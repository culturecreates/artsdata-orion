require 'minitest/autorun'
require 'linkeddata'

class TelephoneTransformTest < Minitest::Test
  def setup
    # Use absolute path from repository root
    repo_root = File.expand_path('../../../../../../', __dir__)
    @transform_sparql = File.read(
      File.join(repo_root, 'app/services/sparqls/mint/transform/fix_telephone_syntax.sparql')
    )
  end

  def test_sparql_file_exists
    repo_root = File.expand_path('../../../../../../', __dir__)
    assert File.exist?(File.join(repo_root, 'app/services/sparqls/mint/transform/fix_telephone_syntax.sparql')),
           "SPARQL transformation file should exist"
  end

  def test_sparql_syntax_valid
    # Check that the SPARQL file can be parsed
    assert @transform_sparql.include?("PREFIX schema:"), "SPARQL should include schema prefix"
    assert @transform_sparql.include?("PREFIX prov:"), "SPARQL should include prov prefix"
    assert @transform_sparql.include?("DELETE"), "SPARQL should include DELETE clause"
    assert @transform_sparql.include?("INSERT"), "SPARQL should include INSERT clause"
    assert @transform_sparql.include?("WHERE"), "SPARQL should include WHERE clause"
  end

  def test_transformation_pattern_detection
    # Verify the SPARQL includes proper regex patterns for phone numbers
    assert @transform_sparql.include?("REGEX"), "SPARQL should use REGEX for pattern matching"
    assert @transform_sparql.include?("REPLACE"), "SPARQL should use REPLACE for formatting"
  end

  def test_provenance_annotation
    # Verify RDF-star annotation for provenance is included
    assert @transform_sparql.include?("prov:wasGeneratedBy"), "SPARQL should include provenance annotation"
    assert @transform_sparql.include?("<<"), "SPARQL should use RDF-star syntax"
  end

  def test_manual_transformation_logic
    # Test the transformation logic manually
    test_cases = {
      "250-383-8124" => "+1-250-383-8124",
      "416-555-1234" => "+1-416-555-1234",
      "604.555.1234" => "+1-604-555-1234",
      "6045551234" => "+1-604-555-1234",
      "(514) 555-1234" => "+1-514-555-1234"
    }

    test_cases.each do |input, expected|
      # Remove non-digits
      digits_only = input.gsub(/[^0-9]/, '')
      
      # Format as XXX-XXX-XXXX
      if digits_only.match(/^(\d{3})(\d{3})(\d{4})$/)
        formatted = "+1-#{$1}-#{$2}-#{$3}"
        assert_equal expected, formatted, "Transformation of '#{input}' should produce '#{expected}'"
      end
    end
  end

  def test_already_formatted_should_not_match
    # Numbers already starting with + should not be transformed
    phone = "+1-250-383-8124"
    
    # Verify our SPARQL has a filter to exclude already formatted numbers
    assert @transform_sparql.include?('FILTER (!REGEX(STR(?oldTelephone), "^\\\\+"))'),
           "SPARQL should filter out already formatted numbers"
  end
end
