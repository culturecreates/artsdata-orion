#!/usr/bin/env ruby
# frozen_string_literal: true

# Preview what artsdata-pipeline-action's UrlFetcher would extract from a
# listing page, without running the action.
#
#   ruby check_selector.rb PAGE_URL ENTITY_IDENTIFIER [--jsonld]
#
# ENTITY_IDENTIFIER is CSS, or XPath when it starts with "/" (same rule as the
# action). For sitemaps (.xml) use "loc". --jsonld also fetches the first
# 3 entity URLs and reports the JSON-LD @type found on each.
#
# This is static HTML only (like the action's default). If the listing is
# built with JavaScript, the action needs `fetch-urls-headlessly: true` and
# this script will report 0 matches.

require 'net/http'
require 'uri'
require 'json'
require 'nokogiri'

UA = 'Mozilla/5.0 (compatible; artsdata-selector-check)'

def get(url, limit = 5)
  uri = URI(url)
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == 'https',
                        open_timeout: 15, read_timeout: 30) do |http|
    http.get(uri.request_uri, 'User-Agent' => UA, 'Accept' => '*/*')
  end
  if res.is_a?(Net::HTTPRedirection) && limit.positive?
    return get(URI.join(url, res['location']).to_s, limit - 1)
  end
  [res, url]
end

page_url, identifier = ARGV.reject { |a| a.start_with?('--') }
abort 'usage: check_selector.rb PAGE_URL ENTITY_IDENTIFIER [--jsonld]' unless page_url && identifier

res, final_url = get(page_url)
puts "HTTP #{res.code}  #{final_url}  (#{res['content-type']})"
puts "  note: redirected from #{page_url}" if final_url != page_url

xml = res['content-type'].to_s.include?('xml') || page_url.end_with?('.xml')
doc = xml ? Nokogiri::XML(res.body) : Nokogiri::HTML(res.body)
doc.remove_namespaces! if xml
nodes = identifier.strip.start_with?('/') ? doc.xpath(identifier) : doc.css(identifier)
puts "Found #{nodes.length} elements matching '#{identifier}'"

urls = nodes.filter_map do |n|
  if xml
    n.content.strip
  else
    href = n['href']
    href && !href.empty? ? URI.join(final_url, href).to_s : nil
  end
end.uniq
missing_href = nodes.length - nodes.count { |n| xml || n['href'] }
puts "  #{missing_href} matched elements have no href (select the <a>, not its container)" if missing_href.positive?
puts "Unique entity URLs: #{urls.length}"
urls.first(10).each { |u| puts "  #{u}" }

if urls.empty? && !xml
  links = doc.css('a[href]').map { |a| a['href'] }.uniq
  puts "\nNo matches. Page has #{links.length} distinct links; sample:"
  links.first(25).each { |h| puts "  #{h}" }
  if res.body.include?('application/ld+json')
    types = res.body.scan(/"@type"\s*:\s*"([^"]+)"/).flatten.tally
    puts "Listing page itself has JSON-LD types: #{types}"
  end
end

if ARGV.include?('--jsonld')
  puts "\nJSON-LD on first entity pages:"
  urls.first(3).each do |u|
    r, = get(u)
    blocks = Nokogiri::HTML(r.body).css('script[type="application/ld+json"]')
    types = blocks.flat_map { |b| b.text.scan(/"@type"\s*:\s*"([^"]+)"/).flatten }.tally
    puts "  #{r.code} #{u}  #{types.empty? ? 'NO JSON-LD' : types}"
  end
end
