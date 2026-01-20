import os
import glob
import json
import re
import copy
from bs4 import BeautifulSoup, Comment
from urllib.parse import urljoin

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(PROJECT_ROOT, 'index.html')
BLOG_DIR = os.path.join(PROJECT_ROOT, 'blog')
DOMAIN = "https://global-apple-id.top"

class SiteBuilder:
    def __init__(self):
        self.assets = {
            'nav': None,
            'footer': None,
            'favicons': [],
            'css_js': []
        }
        self.articles_metadata = []

    def run(self):
        print("🚀 Starting build process...")
        self.step_1_extract_assets()
        self.step_2_scan_articles()
        self.step_3_process_all_pages()
        self.step_4_update_homepage()
        print("✅ Build completed successfully!")

    def read_html(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return BeautifulSoup(f, 'html.parser')

    def save_html(self, soup, path):
        html = str(soup)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    def clean_link(self, url, current_file_path):
        """
        Normalizes links:
        1. Ignores external/special links.
        2. Resolves relative paths to absolute root paths.
        3. Removes .html extension.
        """
        if not url:
            return url
            
        # 1. Ignore Special Protocols & Anchors
        if url.startswith(('http', 'https', 'mailto:', 'tel:', '#', 'javascript:', 'data:')):
            return url
            
        # 2. Resolve Relative to Absolute
        if not url.startswith('/'):
            # Calculate context
            rel_path = os.path.relpath(current_file_path, PROJECT_ROOT)
            base_dir = os.path.dirname(rel_path)
            
            # Base URL path (must end with / for urljoin to work on directory)
            if base_dir:
                base_url_path = f"/{base_dir}/"
            else:
                base_url_path = "/"
            
            # Join (handles ../ automatically)
            url = urljoin(base_url_path, url)
        
        # 3. Remove .html suffix
        if url.endswith('.html'):
            url = url[:-5]
            
        # 4. Clean Trailing Slash (Optional, but 'Clean URL' usually implies no slash for files, but Cloudflare might prefer it? 
        # Project memory says: "Article Pages: No .html extension, no trailing slash")
        if url.endswith('/') and len(url) > 1:
            url = url.rstrip('/')
            
        return url

    def step_1_extract_assets(self):
        print("Phase 1: Smart Extraction from index.html...")
        soup = self.read_html(INDEX_PATH)

        # 1. Extract Nav
        nav = soup.find('nav')
        if nav:
            self.assets['nav'] = nav

        # 2. Extract Footer
        footer = soup.find('footer')
        if footer:
            self.assets['footer'] = footer

        # 3. Extract Brand Assets (Favicons)
        head = soup.find('head')
        if head:
            seen_icons = set()
            for link in head.find_all('link'):
                rel = link.get('rel', [])
                if isinstance(rel, list):
                    rel = " ".join(rel)
                
                if 'icon' in rel:
                    href = link.get('href', '')
                    if href and not href.startswith('http') and not href.startswith('/'):
                        href = '/' + href.lstrip('/')
                    
                    key = (href, rel)
                    if key not in seen_icons:
                        link['href'] = href
                        self.assets['favicons'].append(link)
                        seen_icons.add(key)

            # 4. Extract CSS/JS
            for script in head.find_all('script'):
                if script.get('type') == 'application/ld+json':
                    continue
                self.assets['css_js'].append(script)
            
            for link in head.find_all('link', rel='stylesheet'):
                self.assets['css_js'].append(link)
                
            for style in head.find_all('style'):
                self.assets['css_js'].append(style)

        print(f"   - Extracted Nav, Footer, {len(self.assets['favicons'])} Favicons, {len(self.assets['css_js'])} Resources.")

    def step_2_scan_articles(self):
        print("Phase 2: Scanning Blog Articles...")
        files = glob.glob(os.path.join(BLOG_DIR, '*.html'))
        
        for file_path in files:
            filename = os.path.basename(file_path)
            if filename == 'index.html':
                continue
            
            soup = self.read_html(file_path)
            
            title_tag = soup.find('title')
            title = title_tag.get_text().split('|')[0].strip() if title_tag else "Untitled"
            
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            description = desc_tag['content'] if desc_tag else ""
            
            date = "2026-01-01"
            schema_tag = soup.find('script', type='application/ld+json')
            if schema_tag:
                try:
                    data = json.loads(schema_tag.string)
                    if isinstance(data, dict) and 'datePublished' in data:
                        date = data['datePublished']
                except:
                    pass

            url = f"/blog/{filename.replace('.html', '')}"
            
            self.articles_metadata.append({
                'title': title,
                'description': description,
                'date': date,
                'url': url,
                'file_path': file_path,
                'filename': filename
            })
        
        self.articles_metadata.sort(key=lambda x: x['date'], reverse=True)
        print(f"   - Found {len(self.articles_metadata)} articles.")

    def step_3_process_all_pages(self):
        print("Phase 3: Processing All Pages...")
        
        # 1. Articles
        for article in self.articles_metadata:
            self.process_page(article['file_path'], is_article=True, meta=article)
            
        # 2. Other Pages (Root + Blog Index)
        all_html = glob.glob(os.path.join(PROJECT_ROOT, '**/*.html'), recursive=True)
        for p in all_html:
            # Skip if already processed as article
            if any(p == a['file_path'] for a in self.articles_metadata):
                continue
            
            # Process non-article pages
            self.process_page(p, is_article=False)

    def process_page(self, file_path, is_article=False, meta=None):
        soup = self.read_html(file_path)
        is_index = (file_path == INDEX_PATH)
        filename = os.path.basename(file_path)
        
        # --- A. Link Cleaning & Security ---
        for a in soup.find_all('a', href=True):
            # Clean Link
            a['href'] = self.clean_link(a['href'], file_path)
            
            # External Link Security (noopener)
            href = a['href']
            if href.startswith(('http', 'https')):
                if not href.startswith(DOMAIN): # External
                    rel = a.get('rel', [])
                    if isinstance(rel, str): rel = rel.split()
                    if 'noopener' not in rel: rel.append('noopener')
                    a['rel'] = rel

        # --- B. Layout Sync ---
        # Don't overwrite index layout with itself to avoid potential degradation/loops, 
        # but for others, enforce consistency.
        if not is_index:
            if self.assets['nav']:
                old_nav = soup.find('nav')
                if old_nav:
                    # Preserve any Alpine data if needed? 
                    # The extracted nav is "clean", assume it's the master.
                    # Note: We must clean links in the master nav *before* injection?
                    # Actually, we extracted it in Step 1.
                    # We should probably clean links in the *injected* nav relative to the *target* file?
                    # The extracted nav has "clean" absolute links (from clean_link logic on index.html).
                    # Since they are absolute, they work everywhere.
                    old_nav.replace_with(copy.copy(self.assets['nav']))
                else:
                    if soup.body: soup.body.insert(0, copy.copy(self.assets['nav']))

            if self.assets['footer']:
                old_footer = soup.find('footer')
                if old_footer: old_footer.replace_with(copy.copy(self.assets['footer']))
                else:
                    if soup.body: soup.body.append(copy.copy(self.assets['footer']))

        # --- C. Head Reconstruction (Articles Only) ---
        if is_article and meta:
            head = soup.find('head')
            if not head:
                head = soup.new_tag('head')
                soup.insert(0, head)
            
            original_title = soup.title.string if soup.title else meta['title']
            original_desc = meta['description']
            kw_tag = head.find('meta', attrs={'name': 'keywords'})
            original_keywords = kw_tag['content'] if kw_tag else ""
            
            head.clear()
            
            # Group A
            head.append(soup.new_tag('meta', charset="utf-8"))
            head.append("\n    ")
            head.append(soup.new_tag('meta', attrs={"name": "viewport", "content": "width=device-width, initial-scale=1.0"}))
            head.append("\n    ")
            title_tag = soup.new_tag('title')
            title_tag.string = original_title
            head.append(title_tag)
            head.append("\n\n    ")
            
            # Group B
            if original_desc:
                head.append(soup.new_tag('meta', attrs={"name": "description", "content": original_desc}))
                head.append("\n    ")
            if original_keywords:
                head.append(soup.new_tag('meta', attrs={"name": "keywords", "content": original_keywords}))
                head.append("\n    ")
            canonical_link = soup.new_tag('link', rel="canonical", href=f"{DOMAIN}{meta['url']}")
            head.append(canonical_link)
            head.append("\n\n    ")
            
            # Group C
            head.append(soup.new_tag('meta', attrs={"name": "robots", "content": "index, follow"}))
            head.append("\n    ")
            head.append(soup.new_tag('link', rel="alternate", hreflang="zh", href=f"{DOMAIN}{meta['url']}"))
            head.append("\n    ")
            head.append(soup.new_tag('link', rel="alternate", hreflang="x-default", href=f"{DOMAIN}{meta['url']}"))
            head.append("\n\n    ")
            
            # Group D (Favicons & Resources)
            head.append(Comment(" Favicon "))
            head.append("\n    ")
            for icon in self.assets['favicons']:
                head.append(copy.copy(icon))
                head.append("\n    ")
            
            head.append(Comment(" Resources "))
            head.append("\n    ")
            for res in self.assets['css_js']:
                head.append(copy.copy(res))
                head.append("\n    ")
            head.append("\n\n    ")
            
            # Group E (Schema)
            schema_data = {
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": meta['title'],
                "description": original_desc,
                "author": {"@type": "Organization", "name": "Global Apple ID"},
                "publisher": {
                    "@type": "Organization",
                    "name": "Global Apple ID",
                    "logo": {"@type": "ImageObject", "url": f"{DOMAIN}/logo.png"}
                },
                "datePublished": meta['date'],
                "mainEntityOfPage": {"@type": "WebPage", "@id": f"{DOMAIN}{meta['url']}"}
            }
            script_schema = soup.new_tag('script', type="application/ld+json")
            script_schema.string = json.dumps(schema_data, indent=2, ensure_ascii=False)
            head.append(script_schema)
            
            breadcrumb_data = {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": DOMAIN},
                    {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{DOMAIN}/blog/"},
                    {"@type": "ListItem", "position": 3, "name": meta['title'], "item": f"{DOMAIN}{meta['url']}"}
                ]
            }
            script_breadcrumb = soup.new_tag('script', type="application/ld+json")
            script_breadcrumb.string = json.dumps(breadcrumb_data, indent=2, ensure_ascii=False)
            head.append("\n    ")
            head.append(script_breadcrumb)
            head.append("\n")

        # --- D. Content Injection (Articles Only) ---
        if is_article:
            article_tag = soup.find('article')
            if article_tag:
                rec_section = soup.find('div', id='recommended-reading')
                if not rec_section:
                    rec_section = soup.new_tag('div', id='recommended-reading', attrs={'class': 'mt-12 pt-8 border-t border-slate-200'})
                    article_tag.append(rec_section)
                
                rec_section.clear()
                h3 = soup.new_tag('h3', attrs={'class': 'text-2xl font-bold text-slate-900 mb-6'})
                h3.string = "Recommended Reading"
                rec_section.append(h3)
                
                grid = soup.new_tag('div', attrs={'class': 'grid grid-cols-1 md:grid-cols-2 gap-6'})
                rec_section.append(grid)
                
                count = 0
                for other_meta in self.articles_metadata:
                    if other_meta['filename'] == filename: continue
                    if count >= 2: break
                    
                    card = soup.new_tag('a', href=other_meta['url'], attrs={'class': 'block group bg-slate-50 rounded-xl p-6 border border-slate-100 hover:bg-white hover:shadow-md transition'})
                    title_div = soup.new_tag('h4', attrs={'class': 'font-bold text-slate-900 group-hover:text-brand-600 transition mb-2'})
                    title_div.string = other_meta['title']
                    desc_p = soup.new_tag('p', attrs={'class': 'text-sm text-slate-500 line-clamp-2'})
                    desc_p.string = other_meta['description']
                    
                    card.append(title_div)
                    card.append(desc_p)
                    grid.append(card)
                    count += 1

        # --- E. Missing Schema for Non-Articles ---
        if not is_article and not soup.find('script', type='application/ld+json'):
            # Inject basic WebSite schema
            schema_data = {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": "Global Apple ID",
                "url": DOMAIN
            }
            script_schema = soup.new_tag('script', type="application/ld+json")
            script_schema.string = json.dumps(schema_data, indent=2, ensure_ascii=False)
            if soup.head:
                soup.head.append(script_schema)
            elif soup.body:
                soup.body.insert(0, script_schema)

        self.save_html(soup, file_path)
        print(f"   > Processed {filename}")

    def step_4_update_homepage(self):
        print("Phase 4: Global Update (Homepage)...")
        soup = self.read_html(INDEX_PATH)
        
        blog_header = soup.find(string=re.compile("Latest Tutorials"))
        if blog_header:
            section = blog_header.find_parent('section')
            if section:
                grid = section.find('div', class_=re.compile('grid-cols-1'))
                if grid:
                    grid.clear()
                    
                    for i, meta in enumerate(self.articles_metadata[:3]):
                        colors = ['bg-slate-100', 'bg-red-50', 'bg-indigo-50']
                        icon_colors = ['text-slate-400', 'text-red-300', 'text-indigo-300']
                        icons = ['fa-earth-americas', 'fa-shield-halved', 'fa-user-plus']
                        idx = i % 3
                        
                        article_el = soup.new_tag('article', attrs={'class': 'bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden hover:shadow-xl hover:-translate-y-1 transition duration-300 flex flex-col h-full'})
                        
                        link_block = soup.new_tag('a', href=meta['url'], attrs={'class': f'block h-40 {colors[idx]} relative overflow-hidden group'})
                        icon_div = soup.new_tag('div', attrs={'class': 'absolute inset-0 flex items-center justify-center transition group-hover:bg-opacity-80'})
                        icon_i = soup.new_tag('i', attrs={'class': f'fa-solid {icons[idx]} text-5xl {icon_colors[idx]}'})
                        
                        icon_div.append(icon_i)
                        link_block.append(icon_div)
                        article_el.append(link_block)
                        
                        content_div = soup.new_tag('div', attrs={'class': 'p-5 flex-1 flex flex-col'})
                        
                        date_div = soup.new_tag('div', attrs={'class': 'flex items-center gap-2 text-[10px] text-slate-500 mb-2'})
                        date_span = soup.new_tag('span')
                        date_span.append(soup.new_tag('i', attrs={'class': 'fa-regular fa-calendar mr-1'}))
                        date_span.append(f" {meta['date']}")
                        date_div.append(date_span)
                        content_div.append(date_div)
                        
                        h3 = soup.new_tag('h3', attrs={'class': 'font-bold text-slate-900 mb-2 leading-snug line-clamp-2'})
                        h3_a = soup.new_tag('a', href=meta['url'], attrs={'class': 'hover:text-brand-600 transition'})
                        h3_a.string = meta['title']
                        h3.append(h3_a)
                        content_div.append(h3)
                        
                        p = soup.new_tag('p', attrs={'class': 'text-slate-500 text-xs mb-4 flex-1 line-clamp-3'})
                        p.string = meta['description']
                        content_div.append(p)
                        
                        read_a = soup.new_tag('a', href=meta['url'], attrs={'class': 'text-brand-600 font-bold text-xs hover:underline mt-auto'})
                        read_a.string = "Read Article "
                        read_a.append(soup.new_tag('i', attrs={'class': 'fa-solid fa-arrow-right ml-1'}))
                        content_div.append(read_a)
                        
                        article_el.append(content_div)
                        grid.append(article_el)
                    
                    self.save_html(soup, INDEX_PATH)
                    print("   - Homepage blog section updated.")

if __name__ == "__main__":
    builder = SiteBuilder()
    builder.run()
