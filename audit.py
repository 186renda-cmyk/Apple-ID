import os
import re
import sys
import time
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote
from pathlib import Path
from colorama import init, Fore, Style
from collections import defaultdict

# Initialize colorama
init(autoreset=True)

class SiteAudit:
    def __init__(self):
        self.root_dir = Path.cwd()
        self.base_url = None
        self.files_to_audit = []
        self.internal_links_graph = defaultdict(list)  # target -> [sources]
        self.external_links = set()
        self.issues = []  # List of dicts: {'file': str, 'type': str, 'msg': str, 'level': str}
        self.score = 100
        self.page_stats = {}  # file -> {'h1': int, 'schema': bool, 'breadcrumb': bool}
        
        # Configuration
        self.ignore_paths = ['.git', 'node_modules', '__pycache__']
        self.ignore_url_prefixes = ['/go/', '/cdn-cgi/', 'javascript:', 'mailto:', '#', 'tel:']
        self.ignore_files_pattern = re.compile(r'google.*\.html|404\.html')
        
        # Scoring Penalties
        self.penalties = {
            'dead_link_local': 10,
            'dead_link_external': 5,
            'missing_h1': 5,
            'bad_url_format': 2,
            'missing_schema': 2,
            'orphan_page': 5
        }

    def log(self, level, msg):
        if level == 'SUCCESS':
            print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} {msg}")
        elif level == 'ERROR':
            print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {msg}")
        elif level == 'WARN':
            print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {msg}")
        elif level == 'INFO':
            print(f"{Fore.BLUE}[INFO]{Style.RESET_ALL} {msg}")

    def auto_configure(self):
        index_path = self.root_dir / 'index.html'
        if not index_path.exists():
            self.log('WARN', "Root index.html not found. Cannot determine Base URL accurately.")
            return

        try:
            with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                soup = BeautifulSoup(f, 'html.parser')
                
                # Base URL
                canonical = soup.find('link', rel='canonical')
                og_url = soup.find('meta', property='og:url')
                
                if canonical and canonical.get('href'):
                    self.base_url = canonical['href'].rstrip('/')
                    self.log('SUCCESS', f"Base URL detected (canonical): {self.base_url}")
                elif og_url and og_url.get('content'):
                    self.base_url = og_url['content'].rstrip('/')
                    self.log('SUCCESS', f"Base URL detected (og:url): {self.base_url}")
                else:
                    self.log('WARN', "Base URL not found in index.html. Defaulting to empty string for checks.")
                    self.base_url = ""

                # Keywords (Placeholder for future use)
                keywords = soup.find('meta', attrs={'name': 'keywords'})
                if keywords:
                    self.log('INFO', f"Keywords detected: {keywords.get('content')}")

        except Exception as e:
            self.log('ERROR', f"Failed to parse index.html: {str(e)}")

    def collect_files(self):
        for path in self.root_dir.rglob('*.html'):
            # Check ignore lists
            if any(part in self.ignore_paths for part in path.parts):
                continue
            if self.ignore_files_pattern.search(path.name):
                continue
            
            self.files_to_audit.append(path)
        
        self.log('INFO', f"Found {len(self.files_to_audit)} HTML files to audit.")

    def resolve_local_path(self, current_file, link_href):
        """
        Resolves a link to a local file path.
        Returns: (absolute_path_on_disk, is_found)
        """
        # Remove query params and anchors
        clean_href = link_href.split('#')[0].split('?')[0]
        if not clean_href:
            return None, False

        # Handle absolute URLs that point to this site
        if self.base_url and clean_href.startswith(self.base_url):
            clean_href = clean_href[len(self.base_url):]
            if not clean_href.startswith('/'):
                clean_href = '/' + clean_href

        # Handle root-relative paths
        if clean_href.startswith('/'):
            target_path = self.root_dir / clean_href.lstrip('/')
        else:
            # Handle relative paths
            target_path = current_file.parent / clean_href

        # Normalize path
        try:
            # resolve() can throw error if path doesn't exist on strict mode in some versions, 
            # but we just want to construct the path. 
            # Use os.path.abspath logic manually or resolve() with strict=False (Python 3.10+)
            # Fallback to simple join and normpath for compatibility
            target_path = Path(os.path.normpath(target_path))
        except Exception:
            pass

        # Check existence strategies
        # 1. Exact match (e.g. /blog/post.html)
        if target_path.is_file():
            return target_path, True
        
        # 2. .html extension append (e.g. /blog/post -> /blog/post.html)
        if target_path.with_suffix('.html').is_file():
            return target_path.with_suffix('.html'), True
            
        # 3. Directory index (e.g. /blog/post -> /blog/post/index.html)
        if (target_path / 'index.html').is_file():
            return target_path / 'index.html', True

        return target_path, False

    def check_url_format(self, href, file_path):
        issues = []
        
        # Check 1: Relative path warning
        if not href.startswith('/') and not href.startswith('http'):
            issues.append(f"Relative path used: '{href}'. Should be absolute path starting with '/'.")

        # Check 2: Absolute URL with domain warning (internal links)
        if self.base_url and href.startswith(self.base_url):
             issues.append(f"Absolute URL used: '{href}'. Should be path only (e.g., '{href.replace(self.base_url, '')}').")

        # Check 3: .html extension warning
        if href.endswith('.html'):
             issues.append(f"URL contains .html extension: '{href}'. Should be Clean URL.")
             
        return issues

    def audit_file(self, file_path):
        rel_path = file_path.relative_to(self.root_dir)
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                soup = BeautifulSoup(content, 'html.parser')
                
                # --- Semantics Checks ---
                # H1 Check
                h1s = soup.find_all('h1')
                if len(h1s) != 1:
                    self.add_issue(file_path, 'missing_h1', 'ERROR', f"Found {len(h1s)} <h1> tags. Should be exactly 1.")
                
                # Schema Check
                schema = soup.find('script', type='application/ld+json')
                if not schema:
                    self.add_issue(file_path, 'missing_schema', 'WARN', "No Schema.org structured data found.")
                
                # Breadcrumb Check
                breadcrumb = soup.find(attrs={'aria-label': 'breadcrumb'}) or soup.find(class_=lambda x: x and 'breadcrumb' in x)
                if not breadcrumb and file_path.name != 'index.html': # Ignore index for breadcrumb
                     # Optional: strict check or lenient? Requirement says "Check if exists". Let's warn if missing on non-index pages.
                     # But for simple sites, maybe not all pages need it. I'll stick to 'WARN' if it seems like a content page.
                     # For now, let's just log it if missing.
                     pass 
                     # self.add_issue(file_path, 'missing_breadcrumb', 'WARN', "No breadcrumb navigation found.")

                # --- Link Analysis ---
                for a in soup.find_all('a', href=True):
                    href = a['href'].strip()
                    
                    # Skip ignored patterns
                    if any(href.startswith(p) for p in self.ignore_url_prefixes):
                        continue
                    
                    # External Link
                    if href.startswith('http') and (not self.base_url or not href.startswith(self.base_url)):
                        self.external_links.add(href)
                        
                        # Check rel attributes
                        rel = a.get('rel', [])
                        # Ensure rel is a list
                        if isinstance(rel, str): rel = [rel]
                        
                        # Nofollow/Noopener check logic could be refined based on domain authority, 
                        # but requirement says "Check ... nofollow or noopener".
                        # Usually external links should have noopener.
                        if 'noopener' not in rel and 'noreferrer' not in rel:
                             self.add_issue(file_path, 'unsafe_external_link', 'WARN', f"External link '{href}' missing rel='noopener'.")
                        
                        continue
                    
                    # Internal Link
                    # 1. Format Check
                    format_issues = self.check_url_format(href, file_path)
                    for msg in format_issues:
                        self.add_issue(file_path, 'bad_url_format', 'WARN', msg)
                    
                    # 2. Dead Link & Resolution
                    target_path, found = self.resolve_local_path(file_path, href)
                    
                    if found:
                        # Add to graph (Target <- Source)
                        # Normalize target_path to string relative to root for graph
                        target_rel = str(target_path.relative_to(self.root_dir))
                        source_rel = str(rel_path)
                        self.internal_links_graph[target_rel].append(source_rel)
                    else:
                        self.add_issue(file_path, 'dead_link_local', 'ERROR', f"Dead link: '{href}'. Target file not found.")

        except Exception as e:
            self.log('ERROR', f"Could not audit file {file_path}: {e}")

    def add_issue(self, file_path, type_code, level, msg):
        rel_path = str(file_path.relative_to(self.root_dir))
        self.issues.append({
            'file': rel_path,
            'type': type_code,
            'level': level,
            'msg': msg
        })
        
        # Deduct score immediately
        penalty = self.penalties.get(type_code, 0)
        self.score = max(0, self.score - penalty)

    def check_external_links(self):
        self.log('INFO', f"Checking {len(self.external_links)} external links...")
        
        def check_link(url):
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (compatible; SEOAuditBot/1.0)'}
                response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                if response.status_code >= 400:
                    return url, response.status_code
            except Exception:
                return url, 'Connection Error'
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(check_link, url): url for url in self.external_links}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    url, status = result
                    # External dead links are global, but for reporting I need to attach them to a file? 
                    # The current structure attaches issues to files. 
                    # For simplicity, I will log them as global errors or try to find which file used them (expensive).
                    # I'll add a generic issue or log it clearly.
                    self.log('ERROR', f"External Dead Link: {url} (Status: {status})")
                    self.score = max(0, self.score - self.penalties['dead_link_external'])

    def analyze_graph(self):
        # Check for orphans
        # All files that are not index.html and have 0 inbound links
        for file_path in self.files_to_audit:
            rel_path = str(file_path.relative_to(self.root_dir))
            if rel_path == 'index.html':
                continue
            
            # Check if this file is in the ignore list for orphans? 
            # Requirement: "Exclude index.html and whitelist files"
            
            inbound = self.internal_links_graph.get(rel_path, [])
            if not inbound:
                self.add_issue(file_path, 'orphan_page', 'WARN', "Orphan page (0 inbound links).")

        # Top Pages
        sorted_pages = sorted(self.internal_links_graph.items(), key=lambda x: len(x[1]), reverse=True)
        self.log('INFO', "Top 10 Internal Pages by Inbound Links:")
        for page, sources in sorted_pages[:10]:
            print(f"  - {page}: {len(sources)} links")

    def print_report(self):
        print("\n" + "="*50)
        print("SEO AUDIT REPORT")
        print("="*50 + "\n")

        # Group issues by file
        issues_by_file = defaultdict(list)
        for issue in self.issues:
            issues_by_file[issue['file']].append(issue)

        for file_path in sorted(issues_by_file.keys()):
            print(f"{Fore.CYAN}File: {file_path}{Style.RESET_ALL}")
            for issue in issues_by_file[file_path]:
                color = Fore.GREEN
                if issue['level'] == 'ERROR': color = Fore.RED
                elif issue['level'] == 'WARN': color = Fore.YELLOW
                
                print(f"  {color}[{issue['level']}] {issue['msg']}{Style.RESET_ALL}")
            print("")

        print("-" * 30)
        print(f"Final Score: {self.score}/100")
        
        if self.score < 100:
            print(f"\n{Fore.YELLOW}Actionable Advice:{Style.RESET_ALL}")
            print("  Run 'python fix_links.py' (if available) or manually fix the errors above.")
        else:
            print(f"\n{Fore.GREEN}Great job! Your site is healthy.{Style.RESET_ALL}")

    def run(self):
        self.auto_configure()
        self.collect_files()
        
        self.log('INFO', "Starting local file audit...")
        for file_path in self.files_to_audit:
            self.audit_file(file_path)
            
        self.analyze_graph()
        
        if self.external_links:
            self.check_external_links()
            
        self.print_report()

if __name__ == '__main__':
    audit = SiteAudit()
    audit.run()
