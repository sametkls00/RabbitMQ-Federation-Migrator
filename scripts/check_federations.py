#!/usr/bin/env python3

import requests
import json
import os
import sys
import yaml

# Get variables from environment variables
rabbitmq_host = os.environ.get('OLD_RABBITMQ_HOST')
rabbitmq_port = os.environ.get('OLD_RABBITMQ_PORT', '15672')
rabbitmq_user = os.environ.get('OLD_RABBITMQ_USER', 'devops')
rabbitmq_pass = os.environ.get('OLD_RABBITMQ_PASS', 'Srvhb0420')
rabbitmq_vhost = os.environ.get('OLD_RABBITMQ_VHOST', '%2F')

# Debug environment variables
print("Environment variables:")
print(f"OLD_RABBITMQ_HOST: {rabbitmq_host}")
print(f"OLD_RABBITMQ_PORT: {rabbitmq_port}")
print(f"OLD_RABBITMQ_USER: {rabbitmq_user}")
print(f"OLD_RABBITMQ_VHOST: {rabbitmq_vhost}")

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

def get_federations(host, port, username, password, vhost):
    """
    Get federation configurations from the specified RabbitMQ server
    """
    try:
        # Ensure port is a string
        if port is None or port == "":
            port = "15672"  # Default RabbitMQ management port
        
        # Explicit URL construction with port
        base_url = f"http://{host}:{port}"
        upstream_url = f"{base_url}/api/parameters/federation-upstream/{vhost}"
        policy_url = f"{base_url}/api/policies/{vhost}"
        
        # Debug logging - print the URL we're connecting to
        print(f"Connecting to: {upstream_url}")
        
        # Use direct auth parameter instead of headers
        upstream_response = requests.get(upstream_url, auth=(username, password))
        upstream_response.raise_for_status()
        
        policy_response = requests.get(policy_url, auth=(username, password))
        policy_response.raise_for_status()
        
        upstreams = upstream_response.json()
        policies = [p for p in policy_response.json() if "federation" in json.dumps(p)]
        
        return {"upstreams": upstreams, "policies": policies}
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not get federation information from {host}:{port} - {str(e)}")
        sys.exit(1)

def export_federation_config(federation_data, filename="federation_config.yaml"):
    """
    Export federation configuration to a YAML file
    """
    try:
        with open(filename, 'w') as f:
            yaml.dump(federation_data, f, default_flow_style=False)
        print(f"Federation configuration exported to {filename}")
        return True
    except Exception as e:
        print(f"Error creating configuration file: {str(e)}")
        return False

def get_federation_status(host, port, username, password):
    """
    Get the status of federation links
    """
    try:
        # Ensure port is a string
        if port is None or port == "":
            port = "15672"  # Default RabbitMQ management port
            
        status_url = f"http://{host}:{port}/api/federation-links"
        
        print(f"Checking federation status at: {status_url}")
        
        # Use direct auth parameter instead of headers
        status_response = requests.get(status_url, auth=(username, password))
        status_response.raise_for_status()
        
        return status_response.json()
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not get federation status - {str(e)}")
        return []

def main():
    print("\n=== RabbitMQ Federation Inspector ===\n")
    
    print(f"RabbitMQ: {rabbitmq_host}:{rabbitmq_port}")
    
    # Test authentication
    print("\nTesting authentication with RabbitMQ...")
    if not test_api_auth(rabbitmq_host, rabbitmq_port, rabbitmq_user, rabbitmq_pass):
        print("Authentication failed. Please check credentials.")
        sys.exit(1)
    
    # Get federations from RabbitMQ
    print("\nFetching federation configuration from RabbitMQ...")
    federations = get_federations(rabbitmq_host, rabbitmq_port, rabbitmq_user, rabbitmq_pass, rabbitmq_vhost)
    
    upstream_count = len(federations["upstreams"])
    policy_count = len(federations["policies"])
    
    print(f"Found federation upstreams: {upstream_count}")
    print(f"Found federation policies: {policy_count}")
    
    if upstream_count == 0 and policy_count == 0:
        print("Info: No federations found!")
        sys.exit(0)
    
    # Show upstream details
    print("\nFederation Upstream Details:")
    for idx, upstream in enumerate(federations["upstreams"], 1):
        print(f"\n{idx}. {upstream['name']}")
        print(f"   URI: {upstream['value'].get('uri', 'N/A')}")
        print(f"   Exchange: {upstream['value'].get('exchange', 'N/A')}")
    
    # Show policy details
    print("\nFederation Policy Details:")
    for idx, policy in enumerate(federations["policies"], 1):
        print(f"\n{idx}. {policy['name']}")
        print(f"   Pattern: {policy['pattern']}")
        print(f"   Priority: {policy['priority']}")
        
        # Federation upstreams
        if "federation-upstream" in policy.get("definition", {}):
            upstreams = policy["definition"]["federation-upstream"]
            if isinstance(upstreams, list):
                print(f"   Upstreams: {', '.join(upstreams)}")
            else:
                print(f"   Upstream: {upstreams}")
    
    # Get federation status
    federation_status = get_federation_status(rabbitmq_host, rabbitmq_port, rabbitmq_user, rabbitmq_pass)
    if federation_status:
        print("\nFederation Link Status:")
        for link in federation_status:
            print(f"   {link.get('upstream', 'Unknown')} -> {link.get('exchange', 'Unknown')}: {link.get('status', 'Unknown')}")
    
    # Export federation configuration to file
    export_federation_config(federations)
    
    print("\nInspection completed!")

if __name__ == "__main__":
    main()