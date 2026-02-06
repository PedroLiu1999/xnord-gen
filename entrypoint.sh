#!/bin/sh
set -e

# If the first argument is "fetch-nord-key", run that script
if [ "$1" = "fetch-nord-key" ]; then
    shift
    exec /app/fetch_key.sh "$@"
fi

# Run the config generator
python3 /app/config_generator.py "$@"

# Check if config.json was generated
    echo "Config generated successfully."
    # Xray binary is no longer in this image, so we just exit.
    exit 0
fi

echo "Failed to generate config.json"
exit 1
