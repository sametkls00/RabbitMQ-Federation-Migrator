# RabbitMQ Federation Migrator

A utility script to migrate RabbitMQ federation configurations (upstreams and policies) from one RabbitMQ instance to another.

## Overview

This tool automates the process of transferring federation setups between RabbitMQ instances. It's particularly useful when:
- Migrating to a new RabbitMQ cluster
- Creating a disaster recovery setup
- Duplicating federation configurations across environments

## Features

- Migrates both federation upstreams and policies
- Validates connection to both source and target servers
- Checks if federation plugins are enabled on both servers
- Supports custom virtual hosts
- Exports federation configuration to YAML for backup purposes
- Masks sensitive information (like passwords) in logs and exported configurations
- Progress tracking for migrations with multiple upstreams
- Test mode to validate setup without making changes
- Ability to add a prefix to migrated federation entities

## Requirements

- Python 3.6+
- Dependencies: `requests`, `pyyaml`
- RabbitMQ with federation and federation management plugins enabled on both source and target servers

## Usage

### Environment Variables

The script uses environment variables for configuration:

| Variable | Description | Default |
|----------|-------------|---------|
| `OLD_RABBITMQ_HOST` | Source RabbitMQ hostname/IP | (required) |
| `OLD_RABBITMQ_PORT` | Source RabbitMQ management API port | 15672 |
| `OLD_RABBITMQ_USER` | Source RabbitMQ username | (required) |
| `OLD_RABBITMQ_PASS` | Source RabbitMQ password | (required) |
| `OLD_RABBITMQ_VHOST` | Source RabbitMQ vhost | %2F |
| `NEW_RABBITMQ_HOST` | Target RabbitMQ hostname/IP | (required) |
| `NEW_RABBITMQ_PORT` | Target RabbitMQ management API port | 15672 |
| `NEW_RABBITMQ_USER` | Target RabbitMQ username | (required) |
| `NEW_RABBITMQ_PASS` | Target RabbitMQ password | (required) |
| `NEW_RABBITMQ_VHOST` | Target RabbitMQ vhost | %2F |
| `FEDERATION_PREFIX` | Prefix to add to migrated federation entities | (empty) |
| `VERIFY_FEDERATION` | Verify federation after migration | true |
| `DRY_RUN` | Run without making changes | false |
| `TEST_MODE` | Test connectivity and validation only | false |

### Running with Docker

```bash
docker run \
  -e OLD_RABBITMQ_HOST=source-rabbitmq \
  -e OLD_RABBITMQ_USER=user \
  -e OLD_RABBITMQ_PASS=password \
  -e NEW_RABBITMQ_HOST=target-rabbitmq \
  -e NEW_RABBITMQ_USER=user \
  -e NEW_RABBITMQ_PASS=password \
  your-image-name
```

### Running with GitLab CI

Example `.gitlab-ci.yml`:

```yaml
migrate_federation:
  image: gitlab.example.com/rabbitmq-federation-migrator:latest
  stage: deploy
  variables:
    OLD_RABBITMQ_HOST: "10.0.0.1"
    OLD_RABBITMQ_USER: "username"
    OLD_RABBITMQ_PASS: "${SOURCE_RABBITMQ_PASSWORD}"
    NEW_RABBITMQ_HOST: "10.0.0.2"
    NEW_RABBITMQ_USER: "username"
    NEW_RABBITMQ_PASS: "${TARGET_RABBITMQ_PASSWORD}"
  script:
    - python /app/migrate_federations.py
  artifacts:
    paths:
      - federation_config.yaml
```

## Troubleshooting

### Common Issues

#### 400 Bad Request with "key_missing, value"

If you receive an error like `{"error":"bad_request","reason":"[{key_missing,value}]"}`, this indicates that the RabbitMQ API expects federation upstream parameters in a specific format. The API requires federation upstream values to be sent in a `value` wrapper object.

For example, instead of:
```json
{
  "uri": "amqp://user:pass@host:5672",
  "prefetch-count": 1000
}
```

The API expects:
```json
{
  "value": {
    "uri": "amqp://user:pass@host:5672",
    "prefetch-count": 1000
  }
}
```

The migration script handles this properly by sending the correct format to the API.

#### Federation Upstreams Created But Not Connecting

Verify the following:
1. Ensure that the federation plugin is enabled on both source and target RabbitMQ instances
2. Check if the URIs in the upstreams are correctly formatted (should be `amqp://user:pass@host:5672` using port 5672, not 15672)
3. Confirm network connectivity between the target RabbitMQ and the upstream servers
4. Check RabbitMQ logs for any federation connection errors

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.