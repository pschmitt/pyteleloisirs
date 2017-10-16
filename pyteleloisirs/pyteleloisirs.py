#!/usr/bin/env python
# coding: utf-8

import datetime
import logging


_CACHE = {}
_LOGGER = logging.getLogger(__name__)
BASE_URL = 'http://www.programme-tv.net'


def _request_soup(url):
    '''
    Perform a GET web request and return a bs4 parser
    '''
    import requests
    from bs4 import BeautifulSoup
    _LOGGER.debug('GET %s', url)
    res = requests.get(url)
    res.raise_for_status()
    return BeautifulSoup(res.text, 'html.parser')


def get_channels(no_cache=False, refresh_interval=4):
    '''
    Get channel list and corresponding urls
    '''
    # Check cache
    now = datetime.datetime.now()
    max_cache_age = datetime.timedelta(hours=refresh_interval)
    if not no_cache and 'channels' in _CACHE:
        cache = _CACHE.get('channels')
        cache_age = cache.get('last_updated')
        if now - cache_age < max_cache_age:
            _LOGGER.debug('Found channel list in cache.')
            return cache.get('data')
        else:
            _LOGGER.debug('Found outdated channel list in cache. Update it.')
            _CACHE.pop('channels')
    soup = _request_soup(BASE_URL + '/plan.html')
    channels = {}
    for li_item in soup.find_all('li'):
        child = li_item.findChild()
        if not child or child.name != 'a':
            continue
        href = child.get('href')
        if not href or not href.startswith('/programme/chaine'):
            continue
        channels[child.get('title')] = href
    if channels:
        _CACHE['channels'] = {'last_updated': now, 'data': channels}
    return channels


def get_channel_url(channel):
    '''
    Get the URL of a channel
    '''
    chans = get_channels()
    rel_url = chans.get(channel)
    if rel_url:
        return BASE_URL + rel_url


def extract_program_synopsis(url):
    '''
    Extract the synopsis/summary from a program's detail page
    '''
    soup = _request_soup(url)
    return soup.find(
        'div', {'class': 'episode-synopsis'}).find_all('div')[-1].text.strip()


def get_program_guide(channel, no_cache=False, refresh_interval=4):
    '''
    Get the program data for a channel
    '''
    now = datetime.datetime.now()
    max_cache_age = datetime.timedelta(hours=refresh_interval)
    if not no_cache and 'guide' in _CACHE and _CACHE.get('guide').get(channel):
        cache = _CACHE.get('guide').get(channel)
        cache_age = cache.get('last_updated')
        if now - cache_age < max_cache_age:
            _LOGGER.debug('Found program guide in cache.')
            return cache.get('data')
        else:
            _LOGGER.debug('Found outdated program guide in cache. Update it.')
            _CACHE['guide'].pop(channel)
    url = get_channel_url(channel)
    soup = _request_soup(url)
    programs = []
    for prg_item in soup.find_all('div', {'class': 'program-infos'}):
        prog_info = prg_item.find('a', {'class': 'prog_name'})
        prog_name = prog_info.text.strip()
        prog_url = prog_info.get('href')
        prog_summary = extract_program_synopsis(BASE_URL + prog_url)
        prog_type = prg_item.find('span', {'class': 'prog_type'}).text.strip()
        prog_times = prg_item.find('div', {'class': 'prog_progress'})
        prog_start = datetime.datetime.fromtimestamp(
            int(prog_times.get('data-start')))
        prog_end = datetime.datetime.fromtimestamp(
            int(prog_times.get('data-end')))
        prog_img = prg_item.find_previous_sibling().find(
            'img', {'class': 'prime_broadcast_image'}).get('data-src')
        programs.append(
            {'name': prog_name, 'type': prog_type, 'img': prog_img,
             'summary': prog_summary, 'start_time': prog_start,
             'end_time': prog_end})
    if programs:
        if 'guide' not in _CACHE:
            _CACHE['guide'] = {}
        _CACHE['guide'][channel] = {'last_updated': now, 'data': programs}
    return programs


def get_current_program(channel):
    '''
    Get the current program info
    '''
    guide = get_program_guide(channel)
    now = datetime.datetime.now()
    for prog in guide:
        start = prog.get('start_time')
        end = prog.get('end_time')
        if now > start and now < end:
            return prog
