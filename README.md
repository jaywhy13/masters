Masters Project 2013
=======

# Setup Instructions
```

# Create a local user with sudo priveleges
adduser jay
visudo

sudo apt-get update --fix-missing # necessary for Rackspace
sudo apt-get install python-virtualenv postgresql postgresql-contrib postgresql-server-dev-9.1 git emacs make build-essential libevent-dev python-dev postgis libxml2-dev postgresql-9.1-postgis

pip install psycopg2

# Setup GeoDjango
sudo apt-get install binutils libproj-dev gdal-bin


git clone https://github.com/jaywhy13/masters
git checkout scotland

```
