#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Seed all demo shops, pricing rules, and users into database
python manage.py seed_demo_data

# Automatically create custom superuser if DJANGO_SUPERUSER_PASSWORD is set in Render
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser from environment variables..."
    python manage.py createsuperuser --noinput || true
fi
