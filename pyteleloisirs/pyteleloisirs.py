#!/usr/bin/env python
# coding: utf-8

import asyncio
import datetime
import logging
import re


_CACHE = {}
_LOGGER = logging.getLogger(__name__)
BASE_URL = 'http://www.programme-tv.net'


async def _async_request_soup(url):
    '''
    Perform a GET web request and return a bs4 parser
    '''
    from bs4 import BeautifulSoup
    import aiohttp
    _LOGGER.debug('GET %s', url)
    async with aiohttp.ClientSession() as session:
        resp = await session.get(url)
        text = await resp.text()
        return BeautifulSoup(text, 'html.parser')


async def async_determine_channel(channel):
    '''
    Check whether the current channel is correct. If not try to determine it
    using fuzzywuzzy
    '''
    from fuzzywuzzy import process
    channel_data = await async_get_channels()
    if not channel_data:
        _LOGGER.error('No channel data. Cannot determine requested channel.')
        return
    channels = [c for c in channel_data.get('data', {}).keys()]
    if channel in channels:
        return channel
    else:
        res = process.extractOne(channel, channels)[0]
        _LOGGER.debug('No direct match found for %s. Resort to guesswork.'
                      'Guessed %s', channel, res)
        return res


async def async_get_channels(no_cache=False, refresh_interval=4):
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
            return cache
        else:
            _LOGGER.debug('Found outdated channel list in cache. Update it.')
            _CACHE.pop('channels')
    soup = await _async_request_soup(BASE_URL + '/plan.html')
    channels = {}
    for li_item in soup.find_all('li'):
        try:
            child = li_item.findChild()
            if not child or child.name != 'a':
                continue
            href = child.get('href')
            if not href or not href.startswith('/programme/chaine'):
                continue
            channels[child.get('title')] = BASE_URL + href
        except Exception as exc:
            _LOGGER.error('Exception occured while fetching the channel '
                          'list: %s', exc)
    if channels:
        _CACHE['channels'] = {'last_updated': now, 'data': channels}
        return _CACHE['channels']


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
    # aspect_ratio = res_x / res_y
    target_res_y = int(img_size * res_y / res_x)
    return re.sub(
        r'{}x{}'.format(res_x, res_y),
        r'{}x{}'.format(img_size, target_res_y),
        img_url)


def get_current_program_progress(program):
    '''
    Get the current progress of the program in %
    '''
    now = datetime.datetime.now()
    program_duration = get_program_duration(program)
    if not program_duration:
        return
    progress = now - program.get('start_time')
    return progress.seconds * 100 / program_duration


def get_program_duration(program):
    '''
    Get a program's duration in seconds
    '''
    program_start = program.get('start_time')
    program_end = program.get('end_time')
    if not program_start or not program_end:
        _LOGGER.error('Could not determine program start and/or end times.')
        _LOGGER.debug('Program data: %s', program)
        return
    program_duration = program_end - program_start
    return program_duration.seconds


def get_remaining_time(program):
    '''
    Get the remaining time in seconds of a program that is currently on.
    '''
    now = datetime.datetime.now()
    program_start = program.get('start_time')
    program_end = program.get('end_time')
    if not program_start or not program_end:
        _LOGGER.error('Could not determine program start and/or end times.')
        _LOGGER.debug('Program data: %s', program)
        return
    if now > program_end:
        _LOGGER.error('The provided program has already ended.')
        _LOGGER.debug('Program data: %s', program)
        return 0
    progress = now - program_start
    return progress.seconds


def extract_program_summary(data):
    '''
    Extract the summary data from a program's detail page
    '''
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, 'html.parser')
    try:
        return soup.\
            find('p', {'class': 'synopsis-text'}).\
            text.\
            strip()
    except Exception:
        _LOGGER.info('No summary found for program: %s',
                     soup.find('h1').text.strip())
    finally:
        _LOGGER.info('No summary found nor program name')

    return "No summary"


async def async_set_summary(program):
    '''
    Set a program's summary
    '''
    import aiohttp
    async with aiohttp.ClientSession() as session:
        resp = await session.get(program.get('url'))
        text = await resp.text()
        summary = extract_program_summary(text)
        program['summary'] = summary
        return program


async def async_get_program_guide(channel, no_cache=False, refresh_interval=4):
    '''
    Get the program data for a channel
    '''
    chan = await async_determine_channel(channel)
    now = datetime.datetime.now()
    today = datetime.date.today()
    max_cache_age = datetime.timedelta(hours=refresh_interval)
    if not no_cache and 'guide' in _CACHE and _CACHE.get('guide').get(chan):
        cache = _CACHE.get('guide').get(chan)
        cache_age = cache.get('last_updated')
        if now - cache_age < max_cache_age:
            _LOGGER.debug('Found program guide in cache.')
            return cache.get('data')
        else:
            _LOGGER.debug('Found outdated program guide in cache. Update it.')
            _CACHE['guide'].pop(chan)
    chans = await async_get_channels()
    url = chans.get('data', {}).get(chan)
    if not url:
        _LOGGER.error('Could not determine URL for %s', chan)
        return
    soup = await _async_request_soup(url)
    programs = []
    for prg_item in soup.find_all('div', {'class': 'singleBroadcastCard'}):
        try:
            prog_info = prg_item.find('a', {'class': 'singleBroadcastCard-infos'})
            prog_title = prg_item.find('a', {'class': 'singleBroadcastCard-title'})
            prog_name = prog_title.text.strip()
            prog_url = prog_title.get('href')
            if not prog_url:
                _LOGGER.warning('Failed to retrive the detail URL for program %s. '
                                'The summary will be empty', prog_name)
            prog_type = prg_item.find('div', {'class': 'singleBroadcastCard-genre'}).text.strip()
            prog_times = prg_item.find('span', {'class': 'singleBroadcastCard-durationContent'}).text.strip()
            start_time = prg_item.find('div', {'class': 'singleBroadcastCard-hour'}).text.strip().split('h')
            start_time = [ int(i) for i in start_time ]
            duration = prog_times.replace('min', '').split('h')
            if len(duration) == 1:
                duration.insert(0, 0)
            elif not duration[1]:
                duration[1] = 0
            duration = [ int(i) for i in duration ]
            prog_start = datetime.datetime.combine(today, datetime.time(start_time[0], start_time[1]))
            prog_end = prog_start + datetime.timedelta(hours=duration[0], minutes=duration[1])
            img = prg_item.find('img', {'class': 'apply-ratio'})
            prog_img = img.get('data-src') if img else None
            programs.append(
                {'name': prog_name, 'type': prog_type, 'img': prog_img,
                 'url': prog_url, 'summary': None, 'start_time': prog_start,
                 'end_time': prog_end})
        except Exception as exc:
            _LOGGER.error('Exception occured while fetching the program '
                          'guide for channel %s: %s', chan, exc)
            import traceback
            traceback.print_exc()
    # Set the program summaries asynchronously
    tasks = [async_set_summary(prog) for prog in programs]
    programs = await asyncio.gather(*tasks)
    if programs:
        if 'guide' not in _CACHE:
            _CACHE['guide'] = {}
        _CACHE['guide'][chan] = {'last_updated': now, 'data': programs}
    return programs


async def async_get_current_program(channel, no_cache=False):
    '''
    Get the current program info
    '''
    chan = await async_determine_channel(channel)
    guide = await async_get_program_guide(chan, no_cache)
    if not guide:
        _LOGGER.warning('Could not retrieve TV program for %s', channel)
        return
    now = datetime.datetime.now()
    for prog in guide:
        start = prog.get('start_time')
        end = prog.get('end_time')
        if now > start and now < end:
            return prog


def _request_soup(*args, **kwargs):
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(_async_request_soup(*args, **kwargs))
    return res


def get_channels(*args, **kwargs):
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(async_get_channels(*args, **kwargs))
    return res


def get_program_guide(*args, **kwargs):
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(async_get_program_guide(*args, **kwargs))
    return res


def get_current_program(*args, **kwargs):
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(async_get_current_program(*args, **kwargs))
    return res
