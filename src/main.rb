require 'nokogiri'
require 'open-uri'
require 'linkeddata'

if ARGV.length < 4
  puts "Usage: ruby script_name.rb <page_url> <entity_identifier> <file_name> <is_paginated> <href>
  \n (href is optional in case of data-href tags.)"
  exit
end

def perform_sparql_transformations(graph, sparql_paths, base_url)
  sparql_paths.each do |sparql_path|
    file = File.read(sparql_path).gsub("domain_name", base_url)
    graph.query(SPARQL.parse(file, update: true))
  end
  return graph
end

page_url, entity_identifier, file_name, is_paginated, href = ARGV[0..4]
href = 'href' if !href
base_url = page_url.split('/')[0..2].join('/')
max_retries, retry_count = 3, 0
page_number = is_paginated == 'true' ? 1 : nil
graph = RDF::Graph.new
add_url_sparql_file = File.read('./sparql/add_derived_from.sparql')

entity_urls = []

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
  number_of_entities = entity_urls.length
  entities_data.each do |entity|
    if !entity[href].start_with?('http')
      entity_urls << base_url+entity[href]
    else
      entity_urls << entity[href]
    end
  end
  if entity_urls.length == number_of_entities
    puts "No more entities found on page #{page_number}. Exiting..."
    break
  end

  if page_number.nil?
    break
  else page_number
    page_number += 1
  end
  retry_count = 0
end
entity_urls.uniq!
entity_urls.each do |entity_url|
  begin
    entity_url = entity_url.gsub(' ', '+')
    loaded_graph = RDF::Graph.load(entity_url)
    sparql_file_with_url = add_url_sparql_file.gsub("subject_url", entity_url)
    loaded_graph.query(SPARQL.parse(sparql_file_with_url, update: true))
    graph << loaded_graph
  rescue StandardError => e
    puts "Error loading RDF from #{entity_url}: #{e.message}"
    break
  end
end

sparql_paths = [
  "./sparql/replace_blank_nodes.sparql",
  "./sparql/fix_entity_type_capital.sparql",
  "./sparql/fix_date_timezone.sparql"
]
graph = perform_sparql_transformations(graph, sparql_paths, base_url)

File.open(file_name, 'w') do |file|
  file.puts(graph.dump(:jsonld))
end
