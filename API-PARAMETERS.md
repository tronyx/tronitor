# Parameters
Objects	|      Values      | Extra Details
------- |      ------      |  ----------  
stat | <ul><li>ok</li><li>fail</li></ul> | Exists only for JSON responses to show if any records are returned or not.
pagination>offset |	integer	| The starting record for getMonitors and getAlertContacts methods
pagination>limit | integer | The number of records to be returned for getMonitors and getAlertContacts methods
pagination>total | integer | The total number of records for getMonitors and getAlertContacts methods
account>email | text | The account e-mail.
account>monitor_limit | integer | The max number of monitors that can be created for the account
account>monitor_interval | integer | The min monitoring interval (in seconds) supported by the account
account>up_monitors | integer | The number of "up" monitors
account>down_monitors | integer | The number of "down" monitors
account>pause_monitors | integer | The number of "paused" monitors
monitor>id | integer | The ID of the monitor (can be used for monitor-specific requests).
monitor>friendly_name | text | The friendly name of the monitor.
monitor>url | URL or IP | The URL/IP of the monitor.
monitor>type | <ul><li>1 - HTTP(s)</li><li>2 - Keyword</li><li>3 - Ping</li><li>4 - Port</li></ul> | The type of the monitor.
monitor>sub_type | <ul><li>1 - HTTP (80)</li><li>2 - HTTPS (443)</li><li>3 - FTP (21)</li><li>4 - SMTP (25)</li><li>5 - POP3 (110)</li><li>6 - IMAP (143)</li><li>99 - Custom Port</li></ul> | Used only for "Port monitoring (monitor>type = 4)" and shows which pre-defined port/service is monitored or if a custom port is monitored.
monitor>keyword_type | <ul><li>1 - exists</li><li>2 - not exists</li></ul> | Used only for "Keyword monitoring (monitor>type = 2)" and shows "if the monitor will be flagged as down when the keyword exists or not exists".
monitor>keyword_value	text	the value of the keyword.
monitor>http_username	text	used for password-protected web pages (HTTP Basic Auth). Available for HTTP and keyword monitoring.
monitor>http_password	text	used for password-protected web pages (HTTP Basic Auth). Available for HTTP and keyword monitoring.
monitor>port	integer	used only for "Port monitoring (monitor>type = 4)" and shows the port monitored.
monitor>interval	integer	the interval for the monitoring check (300 seconds by default).
monitor>status
0 - paused
1 - not checked yet
2 - up
8 - seems down
9 - down
the status of the monitor. When used with the editMonitor method 0 (to pause) or 1 (to start) can be sent.
monitor>all_time_uptime_ratio
formatted as up-down-paused

the uptime ratio of the monitor calculated since the monitor is created.
monitor>all_time_uptime_durations
rational number (with 3 decimals)

the durations of all time up-down-paused events in seconds.
monitor>custom_uptime_ratios
rational number (with 3 decimals)

the uptime ratio of the monitor for the given periods (if there is more than 1 period, then the values are seperated with "-")
monitor>custom_uptime_ranges
rational number (with 3 decimals)

the uptime ratio of the monitor for the given ranges (if there is more than 1 range, then the values are seperated with "-")
monitor>average_response_time
rational number (with 3 decimals)

the average value of the response times (requires response_times=1)
log>type
1 - down
2 - up
99 - paused
98 - started
the value of the keyword.
log>datetime	Unix time	the date and time of the log (inherits the user's timezone setting).
log>duration	seconds (integer)	the duration of the downtime in seconds.
log>reason	text	the reason of the downtime (if exists).
response_time>datetime	Unix time	the date and time of the log (inherits the user's timezone setting).
response_time>value	Integer	the time to first-byte in milliseconds.
alertcontact>id	integer	the ID of the alert contact.
alertcontact>type
1 - SMS
2 - E-mail
3 - Twitter DM
4 - Boxcar
5 - Web-Hook
6 - Pushbullet
7 - Zapier
9 - Pushover
10 - HipChat
11 - Slack
the type of the alert contact notified (Zapier, HipChat and Slack are not supported in the newAlertContact method yet).
alertcontact>friendly_name	text	friendly name of the alert contact (for making it easier to distinguish from others).
alertcontact>value	text	alert contact's address/phone.
alertcontact>status
0 - not activated
1 - paused
2 - active
the status of the alert contact.
alertcontact>threshold	0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,20,30,35,40,45,50,55,60,70,80,90,100,110,120,150,180,210,240,270,300,360,420,480,540,600,660,720	the x value that is set to define "if down for x minutes, alert every y minutes.
alertcontact>recurrence	0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,20,30,35,40,45,50,55,60	the y value that is set to define "if down for x minutes, alert every y minutes.
mwindow>id	integer	the ID of the maintenance window.
mwindow>type
1 - Once
2 - Daily
3 - Weekly
4 - Monthly
the type of the maintenance window.
mwindow>friendly_name	text	friendly name of the maintenance window (for making it easier to distinguish from others).
mwindow>value	text	seperated with "-" and used only for weekly and monthly maintenance windows.
mwindow>start_time	Unix time	start time of the maintenance windows.
mwindow>duration	Integer	duration of the maintenance windows in minutes.
mwindow>status
0 - paused
1 - active
the status of the maintenance window.
psp>id	integer	the ID of the status page.
psp>friendly_name	text	friendly name of the status page (for making it easier to distinguish from others).
psp>monitors	text	the list of monitorIDs to be displayed in status page (the values are seperated with "-" or 0 for all monitors).
psp>custom_domain	text	the domain or subdomain that the status page will run on.
psp>password	text	the password for the status page.
psp>sort
1 - friendly name (a-z)
2 - friendly name (z-a)
3 - status (up-down-paused)
4 - status (down-up-paused)
the sorting of the status page.
psp>status
0 - paused
1 - active
the status of the status p
