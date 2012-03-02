#!/usr/bin/python2

import urllib2
import simplejson as json
import string
import time
import ConfigParser
import os


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

  def close_file(self):
    self.fd.close()

  def get_event_set(self, username, start_index):
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
    
    ret = urllib2.urlopen(req).read()
    # output = json.loads(ret)
    # print json.dumps(output, sort_keys=True, indent=4)
    return ret

  def get_and_print_event(self, username, event_id):
    username = username + self.domain
    # auth = urllib2.HTTPDigestAuthHandler()
    # auth.add_password(realm=self.realm,
    #                   uri=self.uri_base,
    #                   user=username,
    #                   passwd=self.cal_passwd)
    # opener = urllib2.build_opener(auth)
    # urllib2.install_opener(opener)


    uri = '%s%s/events/%s' % (self.uri_base, username, event_id)
    print 'fetching: ', uri

    req = urllib2.Request(uri)
    req.add_header('Accept', 'application/json')

    ret = urllib2.urlopen(req).read()
    output = json.loads(ret)
    print json.dumps(output, sort_keys=True, indent=4)
  
  def get_now(self):
    now_secs = time.time()
    now_time = time.localtime(now_secs)
    return int(time.time())
  
  def get_next_event(self, events):
    events = json.loads(events)
    cur_time = self.get_now()
    time_till_next_event = 99999999
    now_event = None
    next_event = None
  
    for event in events['events']:
      if event['recurrence']:
        event = self.find_next_occurrence_of(event, cur_time)
        # print self.display_event(event, "test")
        # self.get_and_print_event('starwars', event['metadata']['id'])
      start_of_this_event = event['start']
      end_of_this_event = event['end']
      if not now_event and self.event_is_happening_now(cur_time, start_of_this_event, end_of_this_event):
        now_event = event
      time_till_start_of_this_event = start_of_this_event - cur_time
      # print "now: ", cur_time
      # print "time till start: ", time_till_start
      # print "next_event_start: ", next_event_start
      # print "--------------------------------------"
      if time_till_start_of_this_event < time_till_next_event and time_till_start_of_this_event > 0:
        next_event = event
    return (now_event, next_event)

  def event_is_happening_now(self, now, event_start, event_end):
    if now > event_start and now < event_end:
      return True
    return False

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

  def record_info(self, string):
    self.fd.write('%s\n' % string)



def main():
  cal = CalendarParser('cal.ini')
  for user in cal.usernames:
    i = 0
    now_event = None
    next_event = None
    print "Fetching records for %s" % user
    while i < 700: 
      print "DEBUG: fetching records %d - %d" % (i, i + 50)
      events = cal.get_event_set(user, i)
      (now, next) = cal.get_next_event(events)
      if now:
        now_event = now
      if next and not next_event:
        next_event = next
      elif next and int(next['start']) < int(next_event['start']):
        next_event = next
      i += 50
    cal.record_info("Room: %s" % user)
    if now_event:
      cal.record_info("Current meeting: %s" % cal.display_event(now_event, user))
      # print "cur %s" % cal.display_event(now_event, user)
    else:
      cal.record_info("Current meeting: AVAILABLE")
      # print 'no cur event'
    if next_event:
      cal.record_info("Next meeting: %s" % cal.display_event(next_event, user))
      # print "next %s" % cal.display_event(next_event, user)
    else:
      cal.record_info("No Future meetings")
      # print 'no next event...?'
    cal.record_info("----------------------")
    # print '----------------------'
    # print json.dumps(next_event, sort_keys=True, indent=4)
    # print "Now is: %s" % time.strftime("%a, %d %b %Y %I:%M:%S ", get_now())
  cal.close_file()

# print json.dumps(output, sort_keys=True, indent=4)

if __name__ == '__main__':
  main()
