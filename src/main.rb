require 'nokogiri'
require 'open-uri'
require 'linkeddata'

if ARGV.length < 4
  puts "Usage: ruby script_name.rb <page_url> <entity_identifier> <file_name> <is_paginated> <base_url>
  \n (base_url is optional in case of relative hrefs)"
  exit
end

page_url = ARGV[0]
entity_identifier = ARGV[1]
file_name = ARGV[2]
is_paginated = ARGV[3]
base_url = ARGV[4] || ''
max_retries, retry_count = 3, 0
page_number = is_paginated == 'true' ? 1 : nil
graph = RDF::Graph.new

loop do
  url = "#{page_url}#{page_number}"
  begin
    main_page_html_text = URI.open(url).read
  rescue StandardError => e
    retry_count += 1
    if retry_count < max_retries
      retry
    else
      puts "Max retries reached. Unable to fetch the content for page #{page_number}."
      break
    end
  end

  main_doc = Nokogiri::HTML(main_page_html_text)
  entities_data = main_doc.css(entity_identifier)
  entity_urls = []
  entities_data.each do |entity|
    entity_urls << base_url+entity['href']
  end
  if entity_urls.empty?
    puts "No more entities found on page #{page_number}. Exiting..."
    break
  end

  entity_urls.each do |entity_url|
    begin
      entity_url = entity_url.gsub(' ', '+')
      graph << RDF::Graph.load(entity_url)
    rescue StandardError => e
      puts "Error loading RDF from #{entity_url}: #{e.message}"
      break
    end
  end
  if page_number == nil
    break
  else
    page_number += 1
  end
  retry_count = 0
end

File.open(file_name, 'w') do |file|
  file.puts(graph.dump(:jsonld))
end
