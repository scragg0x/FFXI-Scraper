import itertools
import os

from gevent.pool import Pool
import requests

import scrapemark
import constants


class DoesNotExist(Exception):
    pass


class Maintenance(Exception):
    pass


class Scraper(object):
    def __init__(self):
        self.s = requests.Session()

    def update_headers(self, headers):
        self.s.headers.update(headers)

    def make_request(self, url=None, body=None, **kwargs):
        url = url.encode('utf-8')
        if body:
            method = 'POST'
        else:
            method = 'GET'

        r = self.s.request(method, url, data=body)

        return {
            'headers': r.headers,
            'content': r.content,
        }

    def scrapemark(self, *args, **kwargs):
        if 'url' in kwargs:
            response = self.make_request(kwargs.pop('url'), **kwargs)
            kwargs['html'] = response['content']

        return scrapemark.scrape(*args, **kwargs)

    def get_pattern(self, pattern_file, **kwargs):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'patterns', pattern_file)) as f:
            pattern = f.read()

            if kwargs:
                pattern = str(pattern % kwargs)

            return pattern


class FFXiScraper(Scraper):
    def __init__(self):
        super(FFXiScraper, self).__init__()

        self.headers = {
            'Accept-Language': 'en-us,en;q=0.5',
            'Cookie': 'LSCOM_TIMEZONE_ID=Europe/London; WORLD_PORTAL_LANGUAGE=;',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6; rv:5.0) Gecko/20100101 Firefox/5.0'
        }

        self.update_headers(self.headers)

    def find_linkshell_url(self, server_name, linkshell_name):
        headers = self.headers.copy()

        world_id = constants.FFXI_SERVER_INDEX[server_name.lower()] - 1

        # Login to Final Fantasy XI Linkshell Community
        login_url = 'http://fanzone.playonline.com/lscom/guestLogin.do?WORLD_ID=1%02d&TIMEZONE_OFFSET=420' % world_id
        response = self.make_request(login_url)

        # Store Cookies
        cookies = self.scrapemark(self.get_pattern('set_cookie.txt'), response['headers']['Set-Cookie'])
        headers['Cookie'] += ' LSCOM_SESSION_ID=%s' % cookies['LSCOM_SESSION_ID']
        self.update_headers(headers)

        # Generate Query String
        params = self.scrapemark(self.get_pattern('server.html'), html=response['content'])
        params['LINKSHELL_NAME'] = linkshell_name
        params['IS_NORMAL_NANE_SEARCH'] = 'true'
        params['CURRENT_PAGE'] = '1'
        params['IS_SELECT_ALL_LANGUAGE'] = 'true'

        querystring = '&'.join([k + '=' + v for k, v in params.items() if v])

        # Search For Linkshell
        search_url = 'http://fanzone.playonline.com/lscom/searchLinkshellName.do?' + querystring
        search = self.scrapemark(self.get_pattern('search.html'), url=search_url, headers=headers)

        url_format = 'http://fanzone.playonline.com/lscom/lscomTop.do?' +\
                     'EQUIP_LINKSHELL_ID_STRING=%(EQUIP_LINKSHELL_ID_STRING)s&' +\
                     'VIEW_LINKSHELL_ID_STRING=%(VIEW_LINKSHELL_ID_STRING)s'

        for result in search['results']:
            if result['name'].lower() == linkshell_name.lower():
                for form in search['forms']:
                    if result['result_id'] == form['result_id']:
                        return url_format % form

        return None

    def find_character_url(self, character_name, linkshell_url):
        # Fetch Linkshell Page
        html = self.make_request(url=linkshell_url, headers=self.headers)['content']

        # Find Character
        form_id = self.scrapemark(self.get_pattern('character_link.html', character=character_name), html=html)

        url_format = 'http://fanzone.playonline.com/lscom/characterAllData.do?' +\
                     'EQUIP_LINKSHELL_ID_STRING=%(EQUIP_LINKSHELL_ID_STRING)s&' +\
                     'VIEW_LINKSHELL_ID_STRING=%(VIEW_LINKSHELL_ID_STRING)s'

        if form_id:
            form = self.scrapemark(self.get_pattern('character_form.html', form_id=form_id), html=html)

            if form:
                return url_format % form

        return None

    def validate_character(self, server_id, character_name, linkshell_names):

        results = []

        pool = Pool()
        # Finds all linkshell URLs

        def find_linkshell_url(linkshell):
            return linkshell, self.find_linkshell_url(server_id, linkshell)

        for linkshell, linkshell_url in itertools.imap(find_linkshell_url, linkshell_names):
            if linkshell_url:
                results.append(dict(ls_name=linkshell,
                                    ls_url=linkshell_url,
                                    char_url=None))
            else:
                results.append(dict(ls_name=linkshell,
                                    ls_url=None,
                                    char_url=None))

        def find_character_url(linkshell):
            # Finds all characters URLs
            linkshell['char_url'] = self.find_character_url(character_name, linkshell['ls_url'])

        for linkshell in results:
            if linkshell.get('ls_url'):
                pool.spawn(find_character_url, linkshell)

        pool.join()

        return results

    def verify_character(self, char_url, verification_code):
        code = self.scrapemark(self.get_pattern('character_comment.html'),
                               url=char_url, headers=self.headers)

        return code and code.strip() == verification_code

    def scrape_character(self, lscom_url):

        # Scrape Character Profile
        data = self.scrapemark(self.get_pattern('character.html'),  url=lscom_url, headers=self.headers)

        # Try again later...
        if data['maintenance'] == 'FINAL FANTASY XI -LINKSHELL COMMUNITY-':
            # TODO: This string is always present, need a different method
            # raise Maintenance()
            pass

        # Character no longer exists?
        if not data['character']:
            raise DoesNotExist()

        try:
            data['server'] = constants.FFXI_SERVER_REVERSE_INDEX[data['server_index']]
        except KeyError:
            raise DoesNotExist

        if not data['privacy']['equip']:

            # Insert slots with no items
            for i in data['empty']:
                for x in ['items', 'item_descriptions', 'item_levels']:
                    data[x].insert(i - 1, None)

            data['equip'] = {}
            data['equip_data'] = {}

            for i in xrange(len(constants.FFXI_SLOTS)):
                data['equip'][constants.FFXI_SLOTS[i]] = data['items'][i]

                if not data['equip_data'].get(constants.FFXI_SLOTS[i]):
                    data['equip_data'][constants.FFXI_SLOTS[i]] = {}

                if data['item_descriptions'][i]:
                    data['item_descriptions'][i] = data['item_descriptions'][i].replace("<br>", "\n")

                if data['item_levels'][i]:
                    data['item_levels'][i] = int(data['item_levels'][i].replace("Lv.", ""))

                data['equip_data'][constants.FFXI_SLOTS[i]]['description'] = data['item_descriptions'][i]
                data['equip_data'][constants.FFXI_SLOTS[i]]['level'] = data['item_levels'][i]

        if data['main_job']:
            data['main_level'] = int(data['main_job'].split(" ")[-1])
            data['main_job'] = constants.FFXI_JOBS_REVERSE[' '.join(data['main_job'].split(" ")[0:-1])].upper()

        if data['sub_job']:
            data['sub_level'] = int(data['sub_job'].split(" ")[-1])
            data['sub_job'] = constants.FFXI_JOBS_REVERSE[' '.join(data['sub_job'].split(" ")[0:-1])].upper()


        data['avatar_url'] = 'http://fanzone.playonline.com' + data['avatar_url']

        # Cleanup
        del data['item_descriptions']
        del data['item_levels']
        del data['maintenance']
        del data['empty']
        del data['items']

        return data

    def scrape_linkshell(self, linkshell_url):

        if not linkshell_url:
            raise DoesNotExist()

        html = self.make_request(linkshell_url, headers=self.headers)['content']

        if '/lscom/error/serverError_us2.html' in html:
            raise DoesNotExist()

        data = self.scrapemark(self.get_pattern('linkshell.html'), html=html)

        if data['maintenance'] == 'MAINTENANCE':
            raise Maintenance()

        try:
            data['server'] = constants.FFXI_SERVER_REVERSE_INDEX[data['server_index']]
        except KeyError:
            raise DoesNotExist

        roster = []

        for member in data['roster']:
            member = {
                'name': member['name'],
                'rank': 'Link' + member['rank'],
                'gender': member['gender'],
                'race': member['race'],
                'jobs': member['jobs'],
                'equip_id': member['equip_id'],
                'view_id': member['view_id']
            }

            if member['rank'] == 'Linkshell':
                member['leader'] = True

            roster.append(member)

        try:
            color = data['roster'][0]['lscolor']
        except (KeyError, IndexError):
            color = None

        return {
            'name': data['name'],
            'server': data['server'],
            'server_index': data['server_index'],
            'color': color,
            'roster': roster
        }
