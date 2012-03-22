#!/usr/bin/python2

#{{{ imports
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
#}}}

#{{{ class CalendarParser
class CalendarParser:
  #{{{ __init__(self, config_file)
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
  #}}}

  #{{{ setup_logging(self, logfile)
  def setup_logging(self, logfile):
    logging.basicConfig(filename=logfile, level=logging.DEBUG, 
        format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S')
    self.logger = logging.getLogger("CalendarParser")
  #}}}

  #{{{ cleanup(self)
  def cleanup(self):
    self.fd.close()
  #}}}

  #{{{ find_next_batch_index(self, events)
  def find_next_batch_index(self, events):
    if events['metadata']['links'].has_key('next'):
      url = events['metadata']['links']['next'][0]['href']
      match = re.search(r'start=(\d+)', url)
      if match:
        return int(match.group(1)) or -1
    return -1
  #}}}

  #{{{ get_event_batch(self, username, start_index)
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
  #}}}

  #{{{ def get_occurrence_list_for_event(self, username, event_id, start_index)
  def get_occurrence_list_for_event(self, username, event_id, start_index):
    username = username + self.domain
    auth = urllib2.HTTPDigestAuthHandler()
    auth.add_password(realm=self.realm,
                      uri=self.uri_base,
                      user=username,
                      passwd=self.cal_passwd)
    opener = urllib2.build_opener(auth)
    urllib2.install_opener(opener)

    uri = "%s%s/events/%s/occurrences?start=%s&limit=50" % (self.uri_base, username, event_id, start_index)
    req = urllib2.Request(uri)
    req.add_header('Accept', 'application/json')
    data = urllib2.urlopen(req).read()
    occurrence_batch = json.loads(data)['occurrences']
    occurrence_index = self.find_next_batch_index(json.loads(data))
    return (occurrence_batch, occurrence_index)
  #}}}
  
  #{{{ find_next_occurrence_of(self, event, cur_time)
  def find_next_occurrence_of(self, event, cur_time):
    event_uri = event['metadata']['links']['via'][0]['href']
    username = re.search(r'user/([\w,\-]+)@', event_uri).group(1)
    event_id = re.search(r'events/(\d+)', event_uri).group(1)
    occurrence_index = 0
    while occurrence_index >= 0:
      (occurrence_batch, occurrence_index) = self.get_occurrence_list_for_event(username, event_id, occurrence_index)
      for occurrence in occurrence_batch:
        if int(occurrence['start']) > cur_time:
          return occurrence
    return event
  #}}}
  
  #{{{ find_cur_and_next_meeting_in_batch(self, event_batch)
  def find_cur_and_next_meeting_in_batch(self, event_batch):
    now = int(time.time())
    secs_until_next_meeting = sys.maxint
    current_meeting = None
    next_meeting = None
  
    for event in event_batch:
      if event['recurrence']:
        event = self.find_next_occurrence_of(event, now)
      try:
        this_event_start = int(event['start'])
        this_event_end = int(event['end'])
      except ValueError, e:
        continue 

      if now > this_event_start and now < this_event_end:
        current_meeting = event
      secs_until_start_of_this_event = this_event_start - now

      if secs_until_start_of_this_event < secs_until_next_meeting and secs_until_start_of_this_event > 0:
        next_meeting = event
        secs_until_next_meeting = secs_until_start_of_this_event
    return (current_meeting, next_meeting)
  #}}}

  #{{{ parse_calendar_for_user(self, user)
  def parse_calendar_for_user(self, user):
    event_index = 0
    current_meeting = None
    next_meeting = None
    logging.info("Fetching records for %s" % user)
    while event_index >= 0:
      (event_batch, next_event_index) = self.get_event_batch(user, event_index)
      logging.debug("Processing records %d - %d" % (event_index + 1, event_index + len(event_batch)))
      (cur_batch_now, cur_batch_next) = self.find_cur_and_next_meeting_in_batch(event_batch)
      current_meeting = current_meeting or cur_batch_now
      next_meeting = next_meeting or cur_batch_next
      if cur_batch_next and int(cur_batch_next['start']) < int(next_meeting['start']):
        next_meeting = cur_batch_next
      event_index = next_event_index
    return (current_meeting, next_meeting)
  #}}}

  #{{{ display_event(self, event, user)
  def display_event(self, event, user):
    subject = event['subject']
    start_secs = event['start']
    start_time = time.localtime(start_secs)
    start_time_str = time.strftime("%a, %m/%d/%Y  %I:%M%p", start_time)
  
    end_secs = event['end']
    end_time = time.localtime(end_secs)
    end_time_str = time.strftime("%I:%M%p", end_time)
    return "\"%s\": %s - %s" % (subject, start_time_str, end_time_str)
  #}}}

  #{{{ record_info(self, string)
  def record_info(self, string):
    self.fd.write('%s\n' % string)
  #}}}

  #{{{ write_meeting_info(self, user, current_event, next_event)
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
  #}}}

#}}}
  

#{{{ parse_args()
def parse_args():
  parser = argparse.ArgumentParser(description='Fetch calendar events')
  parser.add_argument('-c', '--config', dest='config', required=True, 
                      default='test.ini', help='Config file to use')
  return parser.parse_args()
#}}}

#{{{ main()
def main():
  args = parse_args()
  cal = CalendarParser(args.config)
  for user in cal.usernames:
    (current_meeting, next_meeting) = cal.parse_calendar_for_user(user)
    cal.write_meeting_info(user, current_meeting, next_meeting)
  cal.cleanup()
#}}}

if __name__ == '__main__':
  main()
