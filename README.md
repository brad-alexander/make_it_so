# Make It So
Simple configuration management tool

## Python Version

You should be running python 3.7.3.

## Install dependancies

```
pip install -r requirements.txt
```

## Setup your config

The script uses a yaml config file to determine the tasks to be completed.
An example file is in the repo (node_config.yaml).

Here are the parts of the file:
```---
application:
  -
    add_package: <-- additional packages needed
      - php5
      - libapache2-mod-php5
      - php5-mcrypt
    ensure: install <-- action to take on add_package list and name of package, maps to apt-get <ACTION> <package
    name: apache2 <-- name of package to install and service to restart
  -
    templates:  <-- list of files to edit on the target host
      -
        chmod: '646' <-- must set chmod/group/owner to be set for permissions to be set
        group: root
        owner: root
        location: /var/www/html/test.php <-- destination on server
        template_file: test.php <-- name of file in the local templates directory
        params: <-- strings to be changed in the target file
          -
            php_note: "Hello World!!"  <-- __php_note__ in test.php will be changed to "Hello World!!" in file
password: XXXXXX  <-- authentication
username: root
```

## Run your config
```
make_it_so.py --host <IP/HOSTNAME>  --config node_config.yaml
```

## Logging

Logging can be turned off via this line
```logging.basicConfig(level=logging.INFO)```


