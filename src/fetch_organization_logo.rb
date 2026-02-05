require 'linkeddata'
require 'nokogiri'
require 'open-uri'

BASE_URL = "https://recon.artsdata.ca/extend/http%3A%2F%2Fkg.artsdata.ca%2Fcore/Organization"

# rdfs:subClassOf* is not working
ORGANIZATION_SUBTYPES = [
  RDF::Vocab::SCHEMA.PerformingGroup,
  RDF::Vocab::SCHEMA.SportsOrganization,
  RDF::Vocab::SCHEMA.EducationalOrganization,
  RDF::Vocab::SCHEMA.GovernmentOrganization,
  RDF::Vocab::SCHEMA.LocalBusiness,
  RDF::Vocab::SCHEMA.Organization
]

PARENT_TYPES =[
  RDF::Vocab::SCHEMA.WebPage, 
  RDF::Vocab::SCHEMA.WebSite
]

$organization_with_logo_count = 0 
$error_count = 0


def fetch_orgs_with_url(limit = 1000)
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

def extract_logos(graph, organization)
  logo_objects = graph.query([organization, RDF::Vocab::SCHEMA.logo, nil]).map(&:object)
  image_objects = graph.query([organization, RDF::Vocab::SCHEMA.image, nil]).map(&:object)
  logos_and_images = logo_objects + image_objects

  logos = logos_and_images.map do |logo|
    if logo.literal?
      RDF::URI(logo.value)
    elsif logo.uri?
      url = graph.query([logo, RDF::Vocab::SCHEMA.url, nil]).objects.first
      url || logo    
    else
      graph.query([logo, RDF::Vocab::SCHEMA.url, nil]).objects.first
    end
  end.compact.uniq

  logos
end

def extract_types(graph, organization)
  graph.query([organization, RDF.type, nil]).map(&:object)
end

def get_top_level_organizations(graph)
  entities = ORGANIZATION_SUBTYPES.flat_map do |type|
    graph.query([nil, RDF.type, type]).map(&:subject)
  end.uniq
  entities.select { |entity| graph.query([nil, nil, entity]).empty? }
end

def get_embedded_organizations(graph)
  organizations = []

  PARENT_TYPES.each do |parent_type|
    graph.query([nil, RDF.type, parent_type]).each do |stmt|
      parent = stmt.subject

      graph.query([parent, nil, nil]).each do |sub_stmt|
        sub_entity = sub_stmt.object

        next unless sub_entity.is_a?(RDF::URI)

        if ORGANIZATION_SUBTYPES.any? { |t| graph.query([sub_entity, RDF.type, t]).to_a.any? }
          organizations << sub_entity
        end
      end
    end
  end

  organizations.uniq
end

def fetch_organizations_from_graph(graph)
  top_level_organizations = get_top_level_organizations(graph)
  puts "Found #{top_level_organizations.count} top level organizations"
  embedded_organizaions = get_embedded_organizations(graph)
  puts "Found #{embedded_organizaions.count} embedded organizations"
  (top_level_organizations + embedded_organizaions).uniq
end

def build_graph(orgs)
  output_graph = RDF::Graph.new

  orgs.each_with_index do |org, index|
    homepage_url = org['url']
    artsdata_uri = RDF::URI(org['uri'])
    organization_uri = RDF::URI(homepage_url + "#Organization")
    organization_name = org['name']
    puts "Fetching page #{index + 1}/#{orgs.size}, url: #{homepage_url}"

    rdfa_graph = fetch_rdfa(homepage_url)
    begin
      organizations = fetch_organizations_from_graph(rdfa_graph)
      for organization in organizations

        logos = extract_logos(rdfa_graph, organization)
        types = extract_types(rdfa_graph, organization)

        if logos.empty?
          puts "Skipping as no logos exist"
          next
        end

        puts "Found #{logos.size} logos for #{homepage_url} with types #{types.map(&:to_s).join(', ')}"
        $organization_with_logo_count += 1  
        output_graph << [organization_uri, RDF::Vocab::PROV.wasDerivedFrom, RDF::URI(homepage_url)]
        types.each do |t|
          output_graph << [organization_uri, RDF.type, t]
        end        
        output_graph << [organization_uri, RDF::Vocab::SCHEMA.name, organization_name]
        output_graph << [organization_uri, RDF::Vocab::SCHEMA.sameAs, artsdata_uri]

        logos.each_with_index do |logo_uri, i|
          image_object_uri = RDF::URI("#{homepage_url}#ImageObject#{i + 1}")
          domain = URI.parse(homepage_url).host

          output_graph << [organization_uri, RDF::Vocab::SCHEMA.logo, image_object_uri]

          output_graph << [image_object_uri, RDF.type, RDF::Vocab::SCHEMA.ImageObject]
          output_graph << [image_object_uri, RDF::Vocab::SCHEMA.url, logo_uri]
          output_graph << [
            image_object_uri,
            RDF::Vocab::SCHEMA.disambiguatingDescription,
            RDF::Literal.new("Image of #{organization_name}, sourced from #{domain}.")
          ]
          output_graph << [
            image_object_uri,
            RDF::Vocab::SCHEMA.usageInfo,
            RDF::URI("https://kg.artsdata.ca/doc/image-policy")
          ]
        end
      end
    rescue StandardError => e
      warn "Error extracting logos from RDFa graph for #{homepage_url}: #{e.message}"
      next
    end
  end

  output_graph
end

orgs_with_url = fetch_orgs_with_url()
graph = build_graph(orgs_with_url)
File.open("output/organization_logo.jsonld", 'w') do |file|
  file.puts(graph.dump(:jsonld))
end

puts "Total organizations found from recon API: #{orgs_with_url.size}"
puts "Total organizations with logos found: #{$organization_with_logo_count}"
puts "Total errors encountered while loading RDFa: #{$error_count}"
