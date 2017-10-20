#!/usr/bin/env python
# coding: utf-8

import datetime
import logging
import re

import asyncio
import aiohttp


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
        try:
            child = li_item.findChild()
            if not child or child.name != 'a':
                continue
            href = child.get('href')
            if not href or not href.startswith('/programme/chaine'):
                continue
            channels[child.get('title')] = href
        except Exception as exc:
            _LOGGER.error('Exception occured while fetching the channel '
                          'list: %s', exc)
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


def resize_program_image(img_url, img_size=300):
    '''
    Resize a program's thumbnail to the desired dimension
    '''
    match = re.match(r'.+/(\d+)x(\d+)/.+', img_url)
    if not match:
        _LOGGER.warning('Could not compute current image resolution of %s',
                        img_url)
        return img_url
    res_x = int(match.group(1))
    res_y = int(match.group(2))
    aspect_ratio = res_x / res_y
    target_res_y = int(img_size * res_y / res_x)
    return re.sub(
        r'{}x{}'.format(res_x, res_y),
        r'{}x{}'.format(img_size, target_res_y),
        img_url)


async def async_extract_program_summary(data):
    '''
    Extract the summary data from a program's detail page
    '''
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, 'html.parser')
    try:
        return soup.find(
            'div', {'class': 'episode-synopsis'}
        ).find_all('div')[-1].text.strip()
    except Exception as exc:
        _LOGGER.error('Exception during summary extraction: %s', exc)


async def async_set_summary(program):
    '''
    Set a program's summary
    '''
    async with aiohttp.ClientSession() as session:
        async with session.get(program.get('url')) as resp:
            summary = await async_extract_program_summary(await resp.text())
            program['summary'] = summary
            return program


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
    if not url:
        _LOGGER.error('Could not determine URL for %s', channel)
        return
    soup = _request_soup(url)
    programs = []
    for prg_item in soup.find_all('div', {'class': 'program-infos'}):
        try:
            prog_info = prg_item.find('a', {'class': 'prog_name'})
            prog_name = prog_info.text.strip()
            prog_url = prog_info.get('href')
            prog_summary = None
            if prog_url:
                prog_url = BASE_URL + prog_url
            else:
                _LOGGER.warning('Failed to retrive the detail URL for program %s. '
                                'The summary will be empty', prog_name)
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
                 'url': prog_url, 'summary': None, 'start_time': prog_start,
                 'end_time': prog_end})
        except Exception as exc:
            _LOGGER.error('Exception occured while fetching the program '
                          'guide for channel %s: %s', channel, exc)
    # Set the program summaries asynchronously
    loop = asyncio.get_event_loop()
    programs = loop.run_until_complete(
        asyncio.gather(
            *(async_set_summary(prog) for prog in programs)
        )
    )
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
    if not guide:
        _LOGGER.warning('Could not retrieve TV program for %s', channel)
        return
    now = datetime.datetime.now()
    for prog in guide:
        start = prog.get('start_time')
        end = prog.get('end_time')
        if now > start and now < end:
            return prog
