#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Automatically load seed data into production database
if [ -f seed_data.json ]; then
    echo "Loading initial seed data..."
    python manage.py loaddata seed_data.json || true
fi

# Automatically create custom superuser if DJANGO_SUPERUSER_PASSWORD is set in Render
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser from environment variables..."
    python manage.py createsuperuser --noinput || true
fi
