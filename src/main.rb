require_relative 'lib/entity_fetcher'
require_relative 'lib/rdf_processor'
require_relative 'lib/headless_browser'

if ARGV.length < 4
  puts "Usage: ruby script_name.rb <page_url> <entity_identifier> <file_name> <is_paginated> <headless>"
  exit
end

page_url, entity_identifier, file_name, is_paginated, headless = ARGV[0..4]

entity_urls = EntityFetcher.fetch_entity_urls(page_url, entity_identifier, is_paginated)
base_url = page_url.split('/')[0..2].join('/')

if headless == 'true'
  graph = HeadlessBrowser.fetch_json_ld_objects(entity_urls, base_url)
  File.open(file_name, 'w') do |file|
    file.puts(graph.dump(:jsonld))
  end
else
  graph = RDFProcessor.process_rdf(entity_urls, base_url)
  File.open(file_name, 'w') do |file|
    file.puts(graph.dump(:jsonld))
  end
end
