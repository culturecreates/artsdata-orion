require 'linkeddata'
require 'nokogiri'
require 'open-uri'

BASE_URL = "https://staging.recon.artsdata.ca/extend/http%3A%2F%2Fkg.artsdata.ca%2Fcore/Organization"
$organization_with_logo_count = 0 
$error_count = 0


def fetch_orgs_with_url(limit = 200)
  page = 1
  orgs_with_url = []
  retries = 3

  loop do
    url = URI("#{BASE_URL}?page=#{page}&limit=#{limit}")
    puts "Fetching: #{url}"
    begin
      response = Net::HTTP.get_response(url)
      if response.code.to_i >= 500
        raise "Server error: #{response.code}"
      end
    rescue StandardError => e
      warn "Error fetching organizations from #{url}: #{e.message}"
      retries -= 1
      if retries > 0
        warn "Retrying... (#{retries} attempts left)"
        sleep 1
        retry
      else
        warn "Failed to fetch organizations after multiple attempts."
      end
    end
    data = JSON.parse(response.body)

    break if data.empty?

    orgs_with_url.concat(data.select { |item| item['url'] })

    page += 1
  end

  orgs_with_url
end

def fetch_rdfa(homepage_url)
  graph = RDF::Graph.new
  linkeddata_version = Gem::Specification.find_by_name('linkeddata').version.to_s
  headers = { "User-Agent" => "artsdata-crawler/#{linkeddata_version}" }
  begin
    RDF::Reader.for(:rdfa).new(URI.open(homepage_url, headers), base_uri: homepage_url, logger: false) do |reader|
      graph << reader
    end
  rescue StandardError => e
    warn "Error fetching RDFa from #{homepage_url}: #{e.message}"
    $error_count += 1
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
    homepage_url = org['url']
    artsdata_uri = RDF::URI(org['uri'])
    organization_uri = RDF::URI(homepage_url + "#Organization")
    organization_type = org['type'].split(',') || RDF::Vocab::SCHEMA.Organization
    puts "Fetching page #{index + 1}/#{orgs.size}, url: #{homepage_url}"

    rdfa_graph = fetch_rdfa(homepage_url)

    logos = extract_logo(rdfa_graph, RDF::URI(homepage_url))
    next if logos.empty?

    puts "Found #{logos.size} logos for #{homepage_url}"
    $organization_with_logo_count += 1

    organization_type.each do |type|
      output_graph << [organization_uri, RDF.type, RDF::URI(type.strip())]
    end    
    output_graph << [organization_uri, RDF::Vocab::SCHEMA.url, RDF::URI(homepage_url)]
    output_graph << [organization_uri, RDF::Vocab::SCHEMA.name, org['name']]
    output_graph << [organization_uri, RDF::Vocab::SCHEMA.sameAs, artsdata_uri]

    logos.each do |logo|
      output_graph << [organization_uri, RDF::Vocab::SCHEMA.logo, logo]
    end
  end

  output_graph
end

orgs_with_url = fetch_orgs_with_url()
orgs_with_url = orgs_with_url.first(10)
graph = build_graph(orgs_with_url)
File.open("output/organization_logo.jsonld", 'w') do |file|
  file.puts(graph.dump(:jsonld))
end

puts "Total organizations found from recon API: #{orgs_with_url.size}"
puts "Total organizations with logos found: #{$organization_with_logo_count}"
puts "Total errors encountered while loading RDFa: #{$error_count}"