# UptimeRobot Monitor Utility

[![GitHub](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/christronyxyocum/uptimerobot-monitor-utility/blob/develop/LICENSE.md) [![Average time to resolve an issue](http://isitmaintained.com/badge/resolution/christronyxyocum/uptimerobot-monitor-utility.svg)](http://isitmaintained.com/project/christronyxyocum/uptimerobot-monitor-utility "Average time to resolve an issue") [![Percentage of issues still open](http://isitmaintained.com/badge/open/christronyxyocum/uptimerobot-monitor-utility.svg)](http://isitmaintained.com/project/christronyxyocum/uptimerobot-monitor-utility "Percentage of issues still open")

[![Codacy Badge](https://api.codacy.com/project/badge/Grade/da395757a07e45e9a57f8e23bd9aa614)](https://www.codacy.com/app/christronyxyocum/uptimerobot-monitor-utility?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=christronyxyocum/uptimerobot-monitor-utility&amp;utm_campaign=Badge_Grade) [![Build Status](https://travis-ci.org/christronyxyocum/uptimerobot-monitor-utility.svg?branch=develop)](https://travis-ci.org/christronyxyocum/uptimerobot-monitor-utility) [![codecov.io](https://codecov.io/gh/christronyxyocum/uptimerobot-monitor-utility/branch/develop/graphs/badge.svg?branch=develop)](http://codecov.io/github/christronyxyocum/uptimerobot-monitor-utility?branch=develop)

A bash script to work with [UptimeRobot](https://uptimerobot.com) monitors via the API. It checks to make sure that the API key that you provided is valid before performing any requested operations.

## Package Requirements

cURL is required for the script to function as it submits API calls to UptimeRobot. If it is not installed before you execute the script most operations will fail.

It is recommended that you install the JQ package as the script uses it to automatically format the JSON output into a human-readable and colorized output. If you do not install you will see errors about the `jq` command not being found and it may impact the functionality of the script.

```bash
tronyx@suladan:~$ sudo apt install jq
Reading package lists... Done
Building dependency tree
Reading state information... Done
The following NEW packages will be installed:
  jq
0 upgraded, 1 newly installed, 0 to remove and 7 not upgraded.
Need to get 45.6 kB of archives.
After this operation, 90.1 kB of additional disk space will be used.
Get:1 http://archive.ubuntu.com/ubuntu bionic/universe amd64 jq amd64 1.5+dfsg-2 [45.6 kB]
Fetched 45.6 kB in 0s (123 kB/s)
Selecting previously unselected package jq.
(Reading database ... 107503 files and directories currently installed.)
Preparing to unpack .../jq_1.5+dfsg-2_amd64.deb ...
Unpacking jq (1.5+dfsg-2) ...
Setting up jq (1.5+dfsg-2) ...
Processing triggers for man-db (2.8.3-2) ...
```

## Setting it up

To get the script working you will need to clone the repo onto your preferred machine:

```bash
tronyx@suladan:~$ sudo git clone https://github.com/christronyxyocum/uptimerobot-monitor-utility.git
Cloning into 'uptimerobot-monitor-utility'...
remote: Enumerating objects: 108, done.
remote: Counting objects: 100% (108/108), done.
remote: Compressing objects: 100% (75/75), done.
remote: Total 262 (delta 60), reused 76 (delta 32), pack-reused 154
Receiving objects: 100% (262/262), 161.85 KiB | 6.74 MiB/s, done.
Resolving deltas: 100% (143/143), done.
```

Then `cd` into the new directory and make the script executable with the `chmod` command:

```bash
tronyx@suladan:~$ cd uptimerobot-monitor-utility
tronyx@suladan:~/uptimerobot-monitor-utility$ chmod a+x uptimerobot_monitor_utility.sh
```

Finally, open the script with your favorite text editor and add your UptimeRobot API key. If you forget this step the script will prompt you to enter your API key:

![API Key Prompt](/Images/api_key.png)

After entering your API key, the script will check whether or not it is valid and add it to the script for you.

If you are not running the script as the root user, which is recommended, you will need to use `sudo` as the script creates a directory in `/tmp`. The script checks whether or not you're root or are using `sudo` so, if you forget, it will get added for you.

If you use the alert option, be sure to also enter in your Discord/Slack webhook URL. If you forget this as well, the script will also prompt you to enter it:

![Webhook URL Prompt](/Images/webhook_url.png)

## Usage

![Script Usage](/Images/usage.png)

## Examples
### Get account statistics

Display basic statistics for your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -s
Here are the basic statistics for your UptimeRobot account:

{
 "stat": "ok",
 "account": {
   "email": "me@domain.com",
   "monitor_limit": 50,
   "monitor_interval": 5,
   "up_monitors": 14,
   "down_monitors": 0,
   "paused_monitors": 0
 }
}
```

### List all monitors

Display all monitors associated with your account and their current status:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -l
The following UptimeRobot monitors were found in your UptimeRobot account:
Plex (ID: 779783111) - Status: Up
Radarr (ID: 780859973) - Status: Down
Sonarr (ID: 780859962) - Status: Paused
Tautulli (ID: 780859975) - Status: Seems down
```

### Find paused monitors

Find and display all monitors in your account that are currently paused:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -f
The following UptimeRobot monitors are currently paused:
Plex (ID: 779783111)
Radarr (ID: 780859973)
Sonarr (ID: 780859962)
Tautulli (ID: 780859975)

Would you like to unpause the paused monitors? ([Y]es or [N]o):
```

You can also use the `-n` option to display the same list, but not display a prompt to unpause the paused monitors.

### Info

Display all information for a single monitor:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -i 'plex'
{
  "stat": "ok",
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 1
  },
  "monitors": [
    {
      "id": 779783111,
      "friendly_name": "Plex",
      "url": "https://plex.tv",
      "type": 1,
      "sub_type": "",
      "keyword_type": null,
      "keyword_value": "",
      "http_username": "",
      "http_password": "",
      "port": "",
      "interval": 300,
      "status": 2,
      "create_datetime": 1513815865
    }
  ]
}
```

### Get alert contacts

Displays a list of all of the alert contacts configured for the account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -a
The following alert contacts have been found for your UptimeRobot account:

{
  "stat": "ok",
  "offset": 0,
  "limit": 50,
  "total": 2,
  "alert_contacts": [
    {
      "id": "0526944",
      "friendly_name": "E-Mail",
      "type": 2,
      "status": 2,
      "value": "me@domain.com"
    },
    {
      "id": "2611518",
      "friendly_name": "Discord",
      "type": 11,
      "status": 2,
      "value": "https://discordapp.com/api/webhooks/123456789/qwerty-qwerty-qwerty/slack"
    }
  ]
}
```

This can be helpful when creating a new monitor as you can use the `id` field of the alert contact to specify the alert contact that you want to be notified when an event occurs with the new monitor that you're creating.

### Pause all monitors

Pause all monitors in your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -p all
Pausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Pausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}

Pausing Sonarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859962
  }
}

Pausing Tautulli:
{
  "stat": "ok",
  "monitor": {
    "id": 780859975
  }
}
```

### Pause specific monitors

Pause specific monitors in your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -p 'Plex',780859973
Pausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Pausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}
```

### Unpause all monitors

Unpause all monitors in your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -u all
Unpausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Unpausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}

Unpausing Sonarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859962
  }
}

Unpausing Tautulli:
{
  "stat": "ok",
  "monitor": {
    "id": 780859975
  }
}
```

### Unpause specific monitors

Unpause specific monitors in your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -u 'Plex',780859973
Unpausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Unpausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}
```

### Create a new monitor

Monitors can be created using this option.

Modify the settings of the corresponding monitor type JSON file in the `Templates` directory, IE: creating a new HTTP(s) monitor so modify the `Templates/new-http-monitor.json` file. The full API documentation can be found [HERE](https://uptimerobot.com/api) for information on monitor types and any required values and what they're for.

The below example is for creating a new HTTP(s) monitor for Google:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ cat Templates/new-http-monitor.json
{
      "api_key": "",
      "friendly_name": "Google",
      "url": "https://google.com",
      "type": 1,
      "http_username": "",
      "http_password": "",
      "interval": 300,
      "alert_contacts": "",
      "ignore_ssl_errors": "false",
      "format": "json"
}
```

The `api_key` field is filled in automatically by the script, but you can still add it yourself if you'd like to. The `alert_contacts` field can be filled in with the `id` field from your preferred alert contact which you can retrieve using the `-a/--alerts` option with the script.

Then just execute the script to create the monitor:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -c http
{
  "stat": "ok",
  "monitor": {
    "id": 781067574,
    "status": 1
  }
}
```

### Reset a monitor

Reset (deleting all stats and response time data) all or specific monitors in your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -r google

***WARNING*** This will reset ALL data for the specified monitors!!!
Are you sure you wish to continue? ([Y]es or [N]o):
y

Resetting Google:
{
  "stat": "ok",
  "monitor": {
    "id": 781067574
  }
}
```

### Delete a monitor

Delete a specific monitor from your account:

```json
tronyx@suladan:~/uptimerobot-monitor-utility$ sudo ./uptimerobot_monitor_utility.sh -d plex

***WARNING*** This will delete the specified monitor from your account!!!
Are you sure you wish to continue? ([Y]es or [N]o):
y

Deleting Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 781067560
  }
}
```

### Discord alert for paused monitors

Using the `-w` option will check for any paused monitors and, if there are any, send an alert to the specified Discord/Slack webhook like below:

![Discord/Slack Notification](/Images/webhook.png)
