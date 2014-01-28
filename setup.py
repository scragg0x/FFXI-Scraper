from setuptools import setup, find_packages

DESCRIPTION = "FFXI Linkshell Community Scraper"

with open('README.md') as f:
    LONG_DESCRIPTION = f.read()

with open('requirements.txt') as f:
    required = f.read().splitlines()

VERSION = '0.1.5'

CLASSIFIERS = [
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Topic :: Software Development :: Libraries :: Python Modules',
]

setup(name='ffxiscraper',
    version=VERSION,
    packages=find_packages(),
    install_requires=required,
    scripts=['lscom'],
    author='Stanislav Vishnevskiy',
    author_email='vishnevskiy@gmail.com',
    maintainer='Matthew Scragg',
    maintainer_email='scragg@gmail.com',
    url='https://github.com/scragg0x/FFXI-Scraper',
    license='MIT',
    include_package_data=True,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    platforms=['any'],
    classifiers=CLASSIFIERS,
    #test_suite='tests',
)