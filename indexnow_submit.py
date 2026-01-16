import urllib.request
import urllib.error
import json
import xml.etree.ElementTree as ET

# Configuration
API_KEY = "d18753b123184422bd671c0d6263beff"
KEY_LOCATION = "https://global-apple-id.top/d18753b123184422bd671c0d6263beff.txt"
HOST = "global-apple-id.top"
SEARCH_ENGINE_ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_FILE = "sitemap.xml"

def get_urls_from_sitemap(sitemap_path):
    try:
        tree = ET.parse(sitemap_path)
        root = tree.getroot()
        # Handle namespace
        namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = []
        for url in root.findall('ns:url', namespaces):
            loc = url.find('ns:loc', namespaces)
            if loc is not None and loc.text:
                urls.append(loc.text)
        return urls
    except Exception as e:
        print(f"Error parsing sitemap: {e}")
        return []

def submit_to_indexnow(url_list):
    if not url_list:
        print("No URLs to submit.")
        return

    data = {
        "host": HOST,
        "key": API_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": url_list
    }

    try:
        print(f"Submitting {len(url_list)} URLs to {SEARCH_ENGINE_ENDPOINT}...")
        json_data = json.dumps(data).encode('utf-8')
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Content-Length': len(json_data)
        }
        
        req = urllib.request.Request(SEARCH_ENGINE_ENDPOINT, data=json_data, headers=headers, method='POST')
        
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            if status_code in [200, 202]:
                print(f"Success! Status code: {status_code}")
                print("Message: Request processed successfully.")
            else:
                print(f"Response status: {status_code}")
                
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
    except Exception as e:
        print(f"Error sending request: {e}")

if __name__ == "__main__":
    print("Reading URLs from sitemap...")
    urls = get_urls_from_sitemap(SITEMAP_FILE)
    print(f"Found {len(urls)} URLs.")
    
    if urls:
        submit_to_indexnow(urls)
    else:
        print("No URLs found in sitemap to submit.")
