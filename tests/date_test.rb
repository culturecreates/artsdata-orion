require 'minitest/autorun'
require 'linkeddata'

class DateTest < Minitest::Test

  def setup
    @fix_date_sparql_file = './sparql/fix_date.sparql'
  end

  # check that the dates are correctly formatted
  def test_date_format
    sparql = SPARQL.parse(File.read(@fix_date_sparql_file), update: true)
    graph = RDF::Graph.load("./tests/fixtures/test_date.jsonld")
    # puts "before: #{graph.dump(:jsonld)}"
    graph.query(sparql)
    # puts "after: #{graph.dump(:jsonld)}"
    dates = graph.query([nil, RDF::URI("http://schema.org/startDate"), nil]).each.objects
    dates.each do |start_date|
      assert_match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{2}:\d{2}\s*$/, start_date.to_s)
    end
  end
end
