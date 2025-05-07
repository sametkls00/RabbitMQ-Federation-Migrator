#!/usr/bin/env python3

import requests
import json
import os
import sys
import time
import yaml
import re
from urllib.parse import quote_plus

# Get variables from environment variables without defaults for credentials
old_host = os.environ.get('OLD_RABBITMQ_HOST')
old_port = os.environ.get('OLD_RABBITMQ_PORT', '15672')
old_user = os.environ.get('OLD_RABBITMQ_USER')
old_pass = os.environ.get('OLD_RABBITMQ_PASS')
old_vhost = os.environ.get('OLD_RABBITMQ_VHOST', '%2F')  # Default to %2F if empty

new_host = os.environ.get('NEW_RABBITMQ_HOST')
new_port = os.environ.get('NEW_RABBITMQ_PORT', '15672')
new_user = os.environ.get('NEW_RABBITMQ_USER')
new_pass = os.environ.get('NEW_RABBITMQ_PASS')
new_vhost = os.environ.get('NEW_RABBITMQ_VHOST', '%2F')  # Default to %2F if empty

test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'

# Regular operating parameters
federation_prefix = os.environ.get('FEDERATION_PREFIX', '')
verify_federation = os.environ.get('VERIFY_FEDERATION', 'true').lower() == 'true'
dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# Ensure vhosts are not empty - critical fix
if not old_vhost:
    old_vhost = '%2F'
if not new_vhost:
    new_vhost = '%2F'

# Check required variables
missing_vars = []
if not old_host:
    missing_vars.append("OLD_RABBITMQ_HOST")
if not old_user:
    missing_vars.append("OLD_RABBITMQ_USER")
if not old_pass:
    missing_vars.append("OLD_RABBITMQ_PASS")
if not new_host:
    missing_vars.append("NEW_RABBITMQ_HOST")
if not new_user:
    missing_vars.append("NEW_RABBITMQ_USER")
if not new_pass:
    missing_vars.append("NEW_RABBITMQ_PASS")

if missing_vars:
    print(f"Error: The following required environment variables are missing: {', '.join(missing_vars)}")
    sys.exit(1)

# ENHANCEMENT 1: Password masking function
def mask_password_in_uri(uri):
    """
    Mask password in URI for secure logging
    """
    return re.sub(r'(:)([^@:]+)(@)', r'\1****\3', uri)

def get_auth_headers(username, password):
    """
    Create the authorization headers for RabbitMQ HTTP API
    """
    import base64
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

def test_api_auth(host, port, username, password):
    """
    Test API authentication with RabbitMQ
    """
    try:
        url = f"http://{host}:{port}/api/overview"
        print(f"Testing API authentication with {url}")
        print(f"Username: {username}")
        
        # Use basic auth with requests
        response = requests.get(url, auth=(username, password))
        
        if response.status_code == 200:
            print("Authentication successful!")
            return True
        else:
            print(f"Authentication failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error during authentication test: {str(e)}")
        return False

def check_federation_plugin(host, port, username, password):
    """
    Check if federation plugin is enabled on the RabbitMQ server
    """
    try:
        # Check for x-federation-upstream exchange type
        url = f"http://{host}:{port}/api/exchanges"
        print(f"Checking federation plugin at: {url}")
        
        response = requests.get(url, auth=(username, password))
        response.raise_for_status()
        
        exchanges = response.json()
        federation_enabled = any(exchange.get("type") == "x-federation-upstream" for exchange in exchanges)
        
        # Also check if federation API endpoint is accessible
        url = f"http://{host}:{port}/api/federation-links"
        try:
            response = requests.get(url, auth=(username, password))
            if response.status_code == 200:
                federation_mgmt_enabled = True
            else:
                federation_mgmt_enabled = False
        except:
            federation_mgmt_enabled = False
        
        if federation_enabled:
            print("✓ Federation plugin is enabled")
        else:
            print("⚠ Federation plugin might not be enabled (x-federation-upstream exchange type not found)")
            
        if federation_mgmt_enabled:
            print("✓ Federation management plugin is enabled")
        else:
            print("⚠ Federation management plugin might not be enabled (/api/federation-links not accessible)")
            
        return federation_enabled
    except Exception as e:
        print(f"Error checking federation plugin: {str(e)}")
        return False

def get_federations(host, port, username, password, vhost):
    """
    Get federation configurations from the specified RabbitMQ server
    """
    try:
        # Ensure port is a string to avoid issues with string concatenation
        if port is None or port == "":
            port = "15672"  # Default RabbitMQ management port
        
        # Ensure vhost is not empty
        if not vhost:
            vhost = "%2F"
        
        # Explicit URL construction with port
        base_url = f"http://{host}:{port}"
        upstream_url = f"{base_url}/api/parameters/federation-upstream/{vhost}"
        policy_url = f"{base_url}/api/policies/{vhost}"
        
        # Debug logging - print the URL we're connecting to
        print(f"Connecting to: {upstream_url}")
        
        # Federation upstreams - using direct auth parameter
        upstream_response = requests.get(upstream_url, auth=(username, password))
        upstream_response.raise_for_status()
        
        # Federation policies
        policy_response = requests.get(policy_url, auth=(username, password))
        policy_response.raise_for_status()
        
        upstreams = upstream_response.json()
        policies = [p for p in policy_response.json() if "federation" in json.dumps(p)]
        
        return {"upstreams": upstreams, "policies": policies}
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not get federation information from {host}:{port} - {str(e)}")
        sys.exit(1)

def modify_upstream_uri(upstream_value, old_host, new_host):
    """
    Modify the URI in the upstream value object to point to the new host
    instead of creating a circular reference
    """
    if 'uri' in upstream_value:
        # Handle the case where uri is a string
        uri = upstream_value['uri']
        
        # Check if the URI contains the old host name and replace it
        if old_host in uri:
            # Replace the old host with the new host to avoid circular reference
            upstream_value['uri'] = uri.replace(old_host, new_host)
            masked_old = mask_password_in_uri(uri)
            masked_new = mask_password_in_uri(upstream_value['uri'])
            print(f"Modified URI from {masked_old} to {masked_new}")
    
    return upstream_value

def create_federation(host, port, username, password, vhost, federation_data, prefix=""):
    """
    Create federation configurations on the target RabbitMQ server
    """
    # Ensure port is a string
    if port is None or port == "":
        port = "15672"  # Default RabbitMQ management port
    
    # Ensure vhost is not empty
    if not vhost:
        vhost = "%2F"
    
    base_url = f"http://{host}:{port}"
    
    upstream_count = len(federation_data["upstreams"])
    print(f"\nCreating {upstream_count} federation upstreams...")
    
    # Create federation upstreams
    for idx, upstream in enumerate(federation_data["upstreams"], 1):
        upstream_name = upstream["name"]
        # Add prefix (optional)
        new_upstream_name = f"{prefix}{upstream_name}" if prefix else upstream_name
        
        # Progress indicator
        print(f"Processing upstream [{idx}/{upstream_count}]: {new_upstream_name}")
        
        if dry_run or test_mode:
            print(f"{'TEST MODE' if test_mode else 'DRY RUN'}: Would create federation upstream: {new_upstream_name}")
            continue
        
        # Debug the JSON payload with masked password
        if 'uri' in upstream["value"]:
            masked_uri = mask_password_in_uri(upstream["value"]['uri'])
            debug_payload = {
                "ack-mode": upstream["value"].get("ack-mode", "on-confirm"),
                "prefetch-count": upstream["value"].get("prefetch-count", 1000),
                "reconnect-delay": upstream["value"].get("reconnect-delay", 5),
                "trust-user-id": upstream["value"].get("trust-user-id", False),
                "uri": masked_uri
            }
            print(f"JSON Payload (with masked password): {json.dumps(debug_payload)}")
        
        # The correct API endpoint for federation upstreams
        upstream_url = f"{base_url}/api/parameters/federation-upstream/{vhost}/{new_upstream_name}"
        print(f"Creating federation upstream at: {upstream_url}")
        
        try:
            # IMPORTANT: Keep the same JSON structure that was working before
            # Just sending the upstream value directly as it was before
            response = requests.put(
                upstream_url,
                auth=(username, password),
                json=upstream["value"]
            )
            response.raise_for_status()
            print(f"Created federation upstream: {new_upstream_name}")
        except requests.exceptions.RequestException as e:
            print(f"Error: Could not create federation upstream {new_upstream_name} - {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status code: {e.response.status_code}")
                print(f"Response text: {e.response.text}")
    
    policy_count = len(federation_data["policies"])
    print(f"\nCreating {policy_count} federation policies...")
    
    # Create federation policies
    for idx, policy in enumerate(federation_data["policies"], 1):
        policy_name = policy["name"]
        
        # Add prefix (optional)
        new_policy_name = f"{prefix}{policy_name}" if prefix else policy_name
        
        # Progress indicator
        print(f"Processing policy [{idx}/{policy_count}]: {new_policy_name}")
        
        # If we're adding a prefix and the policy uses a federation-upstream, 
        # update the federation-upstream name as well
        if prefix and "definition" in policy and "federation-upstream" in policy["definition"]:
            original_upstream = policy["definition"]["federation-upstream"]
            if isinstance(original_upstream, str):
                policy["definition"]["federation-upstream"] = f"{prefix}{original_upstream}"
            elif isinstance(original_upstream, list):
                policy["definition"]["federation-upstream"] = [f"{prefix}{u}" for u in original_upstream]
        
        if dry_run or test_mode:
            print(f"{'TEST MODE' if test_mode else 'DRY RUN'}: Would create federation policy: {new_policy_name}")
            continue
        
        policy_url = f"{base_url}/api/policies/{vhost}/{new_policy_name}"
        print(f"Creating federation policy at: {policy_url}")
        
        try:
            response = requests.put(
                policy_url,
                auth=(username, password),
                json={
                    "pattern": policy["pattern"],
                    "definition": policy["definition"],
                    "priority": policy["priority"],
                    "apply-to": policy["apply-to"]
                }
            )
            response.raise_for_status()
            print(f"Created federation policy: {new_policy_name}")
        except requests.exceptions.RequestException as e:
            print(f"Error: Could not create federation policy {new_policy_name} - {str(e)}")

def verify_federations(host, port, username, password, vhost, expected_federation_data, prefix=""):
    """
    Verify the created federations
    """
    try:
        # Ensure vhost is not empty
        if not vhost:
            vhost = "%2F"
            
        # Get current federations
        current_federation_data = get_federations(host, port, username, password, vhost)
        
        # Check expected upstream count
        expected_upstream_count = len(expected_federation_data["upstreams"])
        actual_upstream_count = len(current_federation_data["upstreams"])
        
        # Check expected policy count
        expected_policy_count = len(expected_federation_data["policies"])
        actual_policy_count = len([p for p in current_federation_data["policies"] if "federation" in json.dumps(p)])
        
        print(f"\nFederation Verification:")
        print(f"- Expected upstream count: {expected_upstream_count}")
        print(f"- Actual upstream count: {actual_upstream_count}")
        print(f"- Expected federation policy count: {expected_policy_count}")
        print(f"- Actual federation policy count: {actual_policy_count}")
        
        if expected_upstream_count != actual_upstream_count or expected_policy_count != actual_policy_count:
            print("Warning: Federation counts do not match!")
            return False
        
        print("Federation verification successful!")
        return True
        
    except Exception as e:
        print(f"Error during verification: {str(e)}")
        return False

# ENHANCEMENT 5: Automatic backup
def backup_configurations(source_host, source_port, source_user, source_pass, source_vhost,
                          target_host, target_port, target_user, target_pass, target_vhost):
    """
    Create backup of existing federation configurations on both source and target
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    
    try:
        # Backup source configuration
        source_federations = get_federations(source_host, source_port, source_user, source_pass, source_vhost)
        export_federation_config(source_federations, f"source_federation_backup_{timestamp}.yaml")
        
        # Backup target configuration (if any exists)
        try:
            target_federations = get_federations(target_host, target_port, target_user, target_pass, target_vhost)
            if target_federations["upstreams"] or target_federations["policies"]:
                export_federation_config(target_federations, f"target_federation_backup_{timestamp}.yaml")
                print(f"Target federation configuration backed up to target_federation_backup_{timestamp}.yaml")
        except Exception as e:
            print(f"Note: No existing federation configuration found on target or error accessing: {str(e)}")
        
        print(f"Backup completed. Source configuration saved to source_federation_backup_{timestamp}.yaml")
        return True
    except Exception as e:
        print(f"Warning: Failed to create backups: {str(e)}")
        return False

def export_federation_config(federation_data, filename="federation_config.yaml"):
    """
    Export federation configuration to a YAML file
    """
    try:
        # Mask passwords in the URIs before exporting
        masked_data = json.loads(json.dumps(federation_data))
        for upstream in masked_data.get("upstreams", []):
            if "value" in upstream and "uri" in upstream["value"]:
                upstream["value"]["uri"] = mask_password_in_uri(upstream["value"]["uri"])
        
        with open(filename, 'w') as f:
            yaml.dump(masked_data, f, default_flow_style=False)
        print(f"Federation configuration exported to {filename}")
        return True
    except Exception as e:
        print(f"Error creating configuration file: {str(e)}")
        return False

def main():
    print("\n=== RabbitMQ Federation Migrator ===\n")
    
    if test_mode:
        print("TEST MODE ACTIVE - Validating configurations without making changes\n")
    elif dry_run:
        print("DRY RUN MODE ACTIVE - No changes will be made\n")
    
    print(f"Source RabbitMQ: {old_host}:{old_port}")
    print(f"Target RabbitMQ: {new_host}:{new_port}")
    
    # Test authentication with source RabbitMQ
    print("\nTesting authentication with source RabbitMQ...")
    if not test_api_auth(old_host, old_port, old_user, old_pass):
        print("Authentication failed with source RabbitMQ. Please check credentials.")
        sys.exit(1)
    
    # Test authentication with target RabbitMQ
    print("\nTesting authentication with target RabbitMQ...")
    if not test_api_auth(new_host, new_port, new_user, new_pass):
        print("Authentication failed with target RabbitMQ. Please check credentials.")
        sys.exit(1)
    
    # Check federation plugin on both sides
    print("\nChecking federation plugin on source RabbitMQ...")
    source_federation_ok = check_federation_plugin(old_host, old_port, old_user, old_pass)
    
    print("\nChecking federation plugin on target RabbitMQ...")
    target_federation_ok = check_federation_plugin(new_host, new_port, new_user, new_pass)
    
    if not source_federation_ok:
        print("Warning: Federation plugin might not be properly enabled on source RabbitMQ.")
    
    if not target_federation_ok:
        print("Warning: Federation plugin might not be properly enabled on target RabbitMQ.")
        print("This may cause federation upstreams creation to fail.")
        if not test_mode and not dry_run:
            response = input("Do you want to continue anyway? (y/n): ")
            if response.lower() != 'y':
                print("Migration aborted.")
                sys.exit(0)
    
    # Get federations from source RabbitMQ
    print("\nFetching federation configuration from source RabbitMQ...")
    source_federations = get_federations(old_host, old_port, old_user, old_pass, old_vhost)
    
    upstream_count = len(source_federations["upstreams"])
    policy_count = len(source_federations["policies"])
    
    print(f"Found federation upstreams: {upstream_count}")
    print(f"Found federation policies: {policy_count}")
    
    if upstream_count == 0 and policy_count == 0:
        print("Warning: No federations found!")
        sys.exit(0)
    
    # Create backups before making changes
    if not test_mode and not dry_run:
        print("\nCreating backups of existing configurations...")
        backup_configurations(old_host, old_port, old_user, old_pass, old_vhost,
                             new_host, new_port, new_user, new_pass, new_vhost)
    
    # Export federation configuration to file (for reference/backup)
    export_federation_config(source_federations)
    
    # Create federations on target RabbitMQ
    print("\nCreating federations on target RabbitMQ...")
    create_federation(new_host, new_port, new_user, new_pass, new_vhost, source_federations, federation_prefix)
    
    # Verify federations
    if verify_federation and not dry_run and not test_mode:
        print("\nVerifying federations...")
        verify_federations(new_host, new_port, new_user, new_pass, new_vhost, source_federations, federation_prefix)
    
    if test_mode:
        print("\nTest completed! No actual changes were made.")
    else:
        print("\nMigration completed!")

if __name__ == "__main__":
    main()