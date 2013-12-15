Masters Project 2013
=======

# Setup Instructions
```

# Create a local user with sudo priveleges
adduser jay
visudo

sudo apt-get update --fix-missing # necessary for Rackspace
sudo apt-get install python-virtualenv postgresql postgresql-contrib postgresql-server-dev-9.1 git emacs make build-essential libevent-dev python-dev postgis libxml2-dev postgresql-9.1-postgis

# Install PostgiS 1.5
wget https://docs.djangoproject.com/en/dev/_downloads/create_template_postgis-1.5.sh
chmod +x create_template_postgis-1.5.sh
sudo -u postgres ./create_template_postgis-1.5.sh

# Setup GeoDjango
sudo apt-get install binutils libproj-dev gdal-bin python-gdal

# Create the database and user
sudo -u postgres createdb -T template_postgis masters
sudo -u postgres psql
CREATE USER jay WITH PASSWORD 'jay' LOGIN;
GRANT ALL PRIVILEGES ON DATABASE masters to jay;

# Check out the code and install the Python requirements in the VM
git clone https://github.com/jaywhy13/masters
git checkout scotland

source bin/activate
pip install -r requirements.txt





```
