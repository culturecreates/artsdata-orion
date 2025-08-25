require 'linkeddata'
require 'nokogiri'
require 'open-uri'

BASE_URL = "https://staging.recon.artsdata.ca/extend/http%3A%2F%2Fkg.artsdata.ca%2Fcore/Organization"


def fetch_all_urls(limit = 200)
  page = 1
  url_map = []

  loop do
    url = URI("#{BASE_URL}?page=#{page}&limit=#{limit}")
    puts "Fetching: #{url}"
    response = Net::HTTP.get(url)
    data = JSON.parse(response)

    break if data.empty?

    data.each do |item|
      if item['url']
        url_map << { artsdata_uri: item['uri'], homepage: item['url'] }
      end
    end
    page += 1
  end

  url_map
end

def fetch_rdfa(homepage)
  graph = RDF::Graph.new
  begin
    RDF::Reader.for(:rdfa).new(URI.open(homepage), base_uri: homepage, logger: false) do |reader|
      graph << reader
    end
  rescue StandardError => e
    warn "Error fetching RDFa from #{homepage}: #{e.message}"
  end
  graph
end

def extract_logo(graph, org_uri)
  logos = []

  logos += graph.query([nil, RDF::Vocab::SCHEMA.image, nil]).map(&:object)

  logos += graph.query([nil, RDF::Vocab::SCHEMA.logo, nil]).map(&:object)

  graph.query([nil, RDF::Vocab::SCHEMA.image, nil]).each do |stmt|
    img_obj = stmt.object
    graph.query([img_obj, RDF::Vocab::SCHEMA.url, nil]).each do |url_stmt|
      logos << url_stmt.object
    end
  end

  logos.uniq
end

def build_graph(orgs)
  output_graph = RDF::Graph.new

  orgs.each_with_index do |org, index|
    homepage = org[:homepage]
    artsdata_uri = RDF::URI(org[:artsdata_uri])
    puts "Fetching page #{index + 1}/#{orgs.size}, url: #{homepage}"

    rdfa_graph = fetch_rdfa(homepage)

    logos = extract_logo(rdfa_graph, RDF::URI(homepage))
    next if logos.empty?

    output_graph << [artsdata_uri, RDF.type, RDF::Vocab::SCHEMA.Organization]
    output_graph << [artsdata_uri, RDF::Vocab::SCHEMA.url, RDF::URI(homepage)]

    logos.each do |logo|
      output_graph << [artsdata_uri, RDF::Vocab::SCHEMA.logo, logo]
    end
  end

  output_graph
end

artsdata_uri_url_mapping = fetch_all_urls()
graph = build_graph(artsdata_uri_url_mapping)
File.open("output/organization_logo.jsonld", 'w') do |file|
  file.puts(graph.dump(:jsonld))
end