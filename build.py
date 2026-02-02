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
SITEMAP_PATH = os.path.join(PROJECT_ROOT, 'sitemap.xml')
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
        self.sitemap_urls = []

    def run(self):
        print("🚀 Starting build process...")
        self.step_1_extract_assets()
        self.step_2_scan_articles()
        self.step_3_process_all_pages()
        self.step_4_update_homepage()
        self.step_5_generate_sitemap()
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
            
        # 1. Ignore Special Protocols & Anchors (except pure anchors on non-index pages which need fixing later)
        if url.startswith(('http', 'https', 'mailto:', 'tel:', 'javascript:', 'data:')):
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

            # 4. Extract CSS/JS (and Preconnect)
            # Use a set to track seen assets to prevent duplicates
            seen_assets = set()
            
            def add_asset(asset):
                # Generate a unique key for the asset
                if asset.name == 'script':
                    src = asset.get('src')
                    if src:
                        key = ('script', src)
                    else:
                        key = ('script-inline', str(asset.string).strip())
                elif asset.name == 'link':
                    href = asset.get('href')
                    rel = asset.get('rel')
                    if isinstance(rel, list): rel = " ".join(rel)
                    key = ('link', href, rel)
                elif asset.name == 'style':
                    key = ('style', str(asset.string).strip())
                else:
                    key = str(asset)
                
                if key not in seen_assets:
                    self.assets['css_js'].append(asset)
                    seen_assets.add(key)

            for script in head.find_all('script'):
                if script.get('type') == 'application/ld+json':
                    continue
                add_asset(script)
            
            # Extract stylesheets
            for link in head.find_all('link', rel='stylesheet'):
                add_asset(link)
            
            # Extract preconnect
            for link in head.find_all('link', rel='preconnect'):
                add_asset(link)
                
            for style in head.find_all('style'):
                add_asset(style)

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
            raw_title = title_tag.get_text().split('|')[0].strip() if title_tag else "Untitled"
            
            # --- Evergreen Title Cleaning ---
            # Remove years like 2024, 2025, 2026 (with optional brackets/parentheses)
            # Example: "Apple ID 2026 Guide" -> "Apple ID Guide"
            clean_title = re.sub(r'\s*[\(\[\{]?202[0-9]年?[\)\]\}]?\s*', ' ', raw_title)
            # Remove purely numeric segments if user requested "no numbers" broadly, 
            # but usually for SEO "Evergreen" implies removing DATES/YEARS.
            # We also clean up double spaces resulting from removal.
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            description = desc_tag['content'] if desc_tag else ""
            
            # Clean description as well if it contains years
            description = re.sub(r'\s*202[0-9]年?\s*', ' ', description)
            description = re.sub(r'\s+', ' ', description).strip()
            
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
                'title': clean_title,
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
            # Special handling for anchor links on non-index pages
            if not is_index and a['href'].startswith('#'):
                a['href'] = '/' + a['href']
            else:
                # Clean Link
                a['href'] = self.clean_link(a['href'], file_path)
            
            # External Link Security (noopener)
            href = a['href']
            if href.startswith(('http', 'https')):
                if not href.startswith(DOMAIN): # External
                    rel = a.get('rel', [])
                    if isinstance(rel, str): rel = rel.split()
                    if 'noopener' not in rel: rel.append('noopener')
                    if 'nofollow' not in rel: rel.append('nofollow')
                    if 'noreferrer' not in rel: rel.append('noreferrer')
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
            
            # Use meta['title'] (cleaned evergreen version) if available, fallback to existing.
            original_title = meta['title'] if (meta and 'title' in meta) else (soup.title.string if soup.title else "Untitled")
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

            # --- Open Graph & Twitter Cards ---
            head.append(soup.new_tag('meta', attrs={"property": "og:title", "content": original_title}))
            head.append("\n    ")
            if original_desc:
                head.append(soup.new_tag('meta', attrs={"property": "og:description", "content": original_desc}))
                head.append("\n    ")
            head.append(soup.new_tag('meta', attrs={"property": "og:url", "content": f"{DOMAIN}{meta['url']}"}))
            head.append("\n    ")
            head.append(soup.new_tag('meta', attrs={"property": "og:site_name", "content": "Global Apple ID"}))
            head.append("\n    ")
            head.append(soup.new_tag('meta', attrs={"property": "og:type", "content": "article"}))
            head.append("\n    ")
            
            head.append(soup.new_tag('meta', attrs={"name": "twitter:card", "content": "summary"}))
            head.append("\n    ")
            head.append(soup.new_tag('meta', attrs={"name": "twitter:title", "content": original_title}))
            head.append("\n    ")
            if original_desc:
                head.append(soup.new_tag('meta', attrs={"name": "twitter:description", "content": original_desc}))
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
                # Fix Sidebar Sticky
                for div in soup.find_all('div', class_='sticky-card'):
                    div['class'] = ['sticky', 'top-24']

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
                    if count >= 4: break
                    
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

                # --- G. Inject ItemList Schema for Blog Index ---
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        if rel_path == 'blog/index.html':
            # 1. ItemList Schema (Article List)
            item_list_schema = {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": []
            }
            # Use sorted articles_metadata directly
            for i, article in enumerate(self.articles_metadata):
                item_list_schema["itemListElement"].append({
                    "@type": "ListItem",
                    "position": i + 1,
                    "url": f"{DOMAIN}{article['url']}",
                    "name": article['title']
                })
            
            # Remove any duplicate/old schemas first if possible? 
            # Actually, `read_html` reads the file as is. If we append, we might duplicate.
            # But since we overwrite the file at the end, and we just read it from disk...
            # Wait, step_3 runs on *all* pages.
            # If `blog/index.html` is a static file that we are modifying, we should be careful not to append endlessly.
            # However, `read_html` reads the source file. If the source file already has the script, we append another one.
            # Let's clear existing ItemList schemas to be safe.
            for s in soup.find_all('script', type='application/ld+json'):
                if '"ItemList"' in s.string:
                    s.decompose()
            
            script_item_list = soup.new_tag('script', type="application/ld+json")
            script_item_list.string = json.dumps(item_list_schema, indent=2, ensure_ascii=False)
            if soup.head:
                soup.head.append(script_item_list)
            
            # 2. Ensure Breadcrumb Schema exists/is correct
            # (If the static file already has one, we might be duplicating or we can trust it.
            # But usually dynamic is better. Let's check if one exists, if not add it, or replace it?)
            # The user asked to "Increase ... Breadcrumb".
            # The existing file has a breadcrumb. I will assume ItemList is the main addition needed.
            # But I will also force update the Breadcrumb to be safe and dynamic.
            
            # Find existing breadcrumb
            existing_scripts = soup.find_all('script', type='application/ld+json')
            breadcrumb_exists = False
            for s in existing_scripts:
                if '"BreadcrumbList"' in s.string:
                    breadcrumb_exists = True
                    break
            
            if not breadcrumb_exists:
                breadcrumb_data = {
                    "@context": "https://schema.org",
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": DOMAIN},
                        {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{DOMAIN}/blog/"}
                    ]
                }
                script_breadcrumb = soup.new_tag('script', type="application/ld+json")
                script_breadcrumb.string = json.dumps(breadcrumb_data, indent=2, ensure_ascii=False)
                if soup.head:
                    soup.head.append(script_breadcrumb)

        # --- F. Collect URL for Sitemap ---
        # Determine URL
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        if filename == 'index.html':
            if rel_path == 'index.html':
                page_url = '/'
            else:
                # e.g. blog/index.html -> /blog/
                page_url = '/' + os.path.dirname(rel_path) + '/'
        else:
            # e.g. about.html -> /about
            # e.g. blog/post.html -> /blog/post
            base = os.path.splitext(rel_path)[0]
            page_url = '/' + base
        
        # Determine Priority & Frequency
        priority = "0.5"
        freq = "monthly"
        
        if page_url == '/':
            priority = "1.0"
            freq = "daily"
        elif page_url == '/blog/':
            priority = "0.8"
            freq = "weekly"
        elif is_article:
            priority = "0.8"
            freq = "monthly"
        elif page_url in ['/how-to-redeem-gift-cards', '/must-have-apps', '/how-to-change-apple-id-region', '/fix-account-disabled']:
             # Historic high priority pages? Just keeping consistent with old sitemap if needed
             priority = "0.7"
        elif page_url in ['/privacy-policy', '/terms-of-service']:
            priority = "0.3"
            freq = "yearly"
            
        lastmod = meta['date'] if (is_article and meta) else "2026-01-31" # Default to today or file mod time? 
        # Better: if article, use date. If not, use today? 
        # The user wants "Latest article time update".
        
        self.sitemap_urls.append({
            'loc': f"{DOMAIN}{page_url}",
            'lastmod': lastmod,
            'changefreq': freq,
            'priority': priority
        })

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

    def step_5_generate_sitemap(self):
        print("Phase 5: Generating Sitemap...")
        
        # Sort urls: root first, then blog index, then others
        def sort_key(item):
            u = item['loc']
            if u == DOMAIN + '/': return 0
            if u == DOMAIN + '/blog/': return 1
            return 2
        
        self.sitemap_urls.sort(key=sort_key)
        
        xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        for entry in self.sitemap_urls:
            # Skip 404 pages or google verification files if they exist
            if '404' in entry['loc'] or 'google' in entry['loc'] or 'MasterTool' in entry['loc'] or 'SEO_Dashboard' in entry['loc']:
                continue
                
            xml_content.append('  <url>')
            xml_content.append(f"    <loc>{entry['loc']}</loc>")
            xml_content.append(f"    <lastmod>{entry['lastmod']}</lastmod>")
            xml_content.append(f"    <changefreq>{entry['changefreq']}</changefreq>")
            xml_content.append(f"    <priority>{entry['priority']}</priority>")
            xml_content.append('  </url>')
            
        xml_content.append('</urlset>')
        
        with open(SITEMAP_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(xml_content))
            
        print(f"   - Sitemap generated with {len(self.sitemap_urls)} URLs.")

if __name__ == "__main__":
    builder = SiteBuilder()
    builder.run()
