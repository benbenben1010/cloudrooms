#!/usr/bin/python2

import argparse
import ConfigParser
import logging
import os
import re
import simplejson as json
import string
import sys
import time
import urllib2

class CalendarParser:
  def __init__(self, config_file):
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    self.uri_base = config.get('DEFAULT', 'uri_base')
    self.cal_passwd = config.get('DEFAULT', 'cal_passwd')
    self.usernames = config.get('DEFAULT', 'usernames').split(',')
    self.domain = config.get('DEFAULT', 'domain')
    self.realm = config.get('DEFAULT', 'realm')
    self.outfile = config.get('DEFAULT', 'outfile')
    if os.path.exists(self.outfile):
      os.remove(self.outfile)
    self.fd = open(self.outfile, 'w')

    self.setup_logging(config.get('DEFAULT', 'logfile'))

  def setup_logging(self, logfile):
    logging.basicConfig(filename=logfile, level=logging.DEBUG, 
        format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S')
    self.logger = logging.getLogger("CalendarParser")

  def cleanup(self):
    self.fd.close()

  def get_event_batch(self, username, start_index):
    username = username + self.domain
    auth = urllib2.HTTPDigestAuthHandler()
    auth.add_password(realm=self.realm,
                      uri=self.uri_base,
                      user=username,
                      passwd=self.cal_passwd)
    opener = urllib2.build_opener(auth)
    urllib2.install_opener(opener)
  
    uri =  '%s%s/events?start=%s&limit=50' % (self.uri_base, username, start_index)
    
    req = urllib2.Request(uri)
    req.add_header('Accept', 'application/json')
    
    data = urllib2.urlopen(req).read()
    event_batch = json.loads(data)['events']
    event_index = self.find_next_batch_index(json.loads(data))
    return (event_batch, event_index)

  def get_current_time(self):
    return int(time.time())
  
  def find_next_events_in_batch(self, events):
    cur_time = self.get_current_time()
    time_till_next_event = sys.maxint
    now_event = None
    next_event = None
  
    for event in events:
      if event['recurrence']:
        event = self.find_next_occurrence_of(event, cur_time)
      try:
        start_of_this_event = int(event['start'])
        end_of_this_event = int(event['end'])
      except ValueError, e:
        continue 
      if not now_event and self.event_is_happening_now(cur_time, start_of_this_event, end_of_this_event):
        now_event = event
      time_till_start_of_this_event = start_of_this_event - cur_time
      if time_till_start_of_this_event < time_till_next_event and time_till_start_of_this_event > 0:
        next_event = event
    return (now_event, next_event)

  def event_is_happening_now(self, now, event_start, event_end):
    return now > event_start and now < event_end

  def find_next_occurrence_of(self, event, cur_time):
    if event['recurrence'].has_key('until'):
      until_time = event['recurrence']['until']
      total_count = 99999999
    elif event['recurrence'].has_key('count'):
      until_time = 9999999999
      total_count = int(event['recurrence']['count'])
    else:
      until_time = 9999999999
      total_count = 9999999

    event_start = time.localtime(event['start'])
    event_end = time.localtime(event['end'])

    if event['recurrence']['type'] == 'weekly':
      interval = int(event['recurrence']['interval'])
      while event['start'] < cur_time and event['start'] < until_time and total_count > 0:
        event['start'] += (60 * 60 * 24 * 7 * interval)
        event['end'] += (60 * 60 * 24 * 7 * interval)
        total_count -= 1
      return event
    return event
  
  def display_event(self, event, user):
    subject = event['subject']
    start_secs = event['start']
    start_time = time.localtime(start_secs)
    start_time_str = time.strftime("%a, %d %b %Y %I:%M:%S %p", start_time)
  
    end_secs = event['end']
    end_time = time.localtime(end_secs)
    end_time_str = time.strftime("%a, %d %b %Y %I:%M:%S %p", end_time)
    return "Event: \"%s\", from %s - %s" % (subject, start_time_str, end_time_str)

  def find_next_batch_index(self, events):
    if events['metadata']['links'].has_key('next'):
      url = events['metadata']['links']['next'][0]['href']
      match = re.search(r'start=(\d+)', url)
      if match:
        return int(match.group(1)) or -1
    return -1

  def parse_calendar_for_user(self, user):
    event_index = 0
    current_meeting = None
    next_meeting = None
    logging.info("Fetching records for %s" % user)
    while event_index >= 0:
      (event_batch, next_event_index) = self.get_event_batch(user, event_index)
      logging.debug("Processing records %d - %d" % (event_index + 1, event_index + len(event_batch)))
      (cur_batch_now, cur_batch_next) = self.find_next_events_in_batch(event_batch)
      current_meeting = current_meeting or cur_batch_now
      next_meeting = next_meeting or cur_batch_next
      if cur_batch_next and int(cur_batch_next['start']) < int(next_meeting['start']):
        next_meeting = cur_batch_next
      event_index = next_event_index
    return (current_meeting, next_meeting)

  def write_meeting_info(self, user, current_event, next_event):
    self.record_info("Room: %s" % user)
    if current_event:
      self.record_info("Current meeting: %s" % self.display_event(current_event, user))
    else:
      self.record_info("Current meeting: AVAILABLE")
    if next_event:
      self.record_info("Next meeting: %s" % self.display_event(next_event, user))
    else:
      self.record_info("No Future meetings")
    self.record_info("----------------------")

  def record_info(self, string):
    self.fd.write('%s\n' % string)

  #TODO: Only for debugging; delete when finished
  def get_and_print_event(self, username, event_id):
    username = username + self.domain

    uri = '%s%s/events/%s' % (self.uri_base, username, event_id)
    print 'fetching: ', uri

    req = urllib2.Request(uri)
    req.add_header('Accept', 'application/json')

    ret = urllib2.urlopen(req).read()
    output = json.loads(ret)
    print json.dumps(output, sort_keys=True, indent=4)
    return output
  

def parse_args():
  parser = argparse.ArgumentParser(description='Fetch calendar events')
  parser.add_argument('-c', '--config', dest='config', required=True, 
                      default='test.ini', help='Config file to use')
  return parser.parse_args()

def main():
  args = parse_args()
  cal = CalendarParser(args.config)
  for user in cal.usernames:
    (current_meeting, next_meeting) = cal.parse_calendar_for_user(user)
    cal.write_meeting_info(user, current_meeting, next_meeting)
  cal.cleanup()

# print json.dumps(output, sort_keys=True, indent=4)

if __name__ == '__main__':
  main()
