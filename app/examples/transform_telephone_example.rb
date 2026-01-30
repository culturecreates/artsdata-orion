#!/usr/bin/env ruby

# Example script demonstrating telephone number transformation
# Usage: ruby app/examples/transform_telephone_example.rb

require_relative '../services/mint_service'
require 'linkeddata'

# Create a sample graph with organization data including telephone numbers
graph = RDF::Graph.new

# Example 1: Organization with telephone in format from issue
org1 = RDF::URI("http://example.org/organizations/1")
graph << [org1, RDF.type, RDF::Vocab::SCHEMA.Organization]
graph << [org1, RDF::Vocab::SCHEMA.name, "Example Organization 1"]
graph << [org1, RDF::Vocab::SCHEMA.telephone, "250-383-8124"]

# Example 2: Organization with different format
org2 = RDF::URI("http://example.org/organizations/2")
graph << [org2, RDF.type, RDF::Vocab::SCHEMA.Organization]
graph << [org2, RDF::Vocab::SCHEMA.name, "Example Organization 2"]
graph << [org2, RDF::Vocab::SCHEMA.telephone, "(416) 555-1234"]

# Example 3: Organization with already formatted telephone
org3 = RDF::URI("http://example.org/organizations/3")
graph << [org3, RDF.type, RDF::Vocab::SCHEMA.Organization]
graph << [org3, RDF::Vocab::SCHEMA.name, "Example Organization 3"]
graph << [org3, RDF::Vocab::SCHEMA.telephone, "+1-604-555-6789"]

puts "Original graph:"
puts "=" * 60
graph.each { |stmt| puts stmt.to_ntriples }
puts

# Transform the graph
transformed_graph = MintService.transform_graph(graph)

puts "Transformed graph:"
puts "=" * 60
transformed_graph.each { |stmt| puts stmt.to_ntriples }
puts

# Show telephone numbers before and after
puts "Telephone transformations:"
puts "=" * 60
[org1, org2, org3].each do |org|
  name = graph.query([org, RDF::Vocab::SCHEMA.name, nil]).first&.object
  old_tel = graph.query([org, RDF::Vocab::SCHEMA.telephone, nil]).first&.object
  new_tel = transformed_graph.query([org, RDF::Vocab::SCHEMA.telephone, nil]).first&.object
  
  puts "#{name}:"
  puts "  Before: #{old_tel}"
  puts "  After:  #{new_tel}"
  puts "  Status: #{old_tel == new_tel ? 'No change' : 'Transformed ✓'}"
  puts
end
