# Links a source log (GitHub issue) to one or more Artsdata graphs.
#
# This script holds no SPARQL of its own. It calls nebula's
# ArtifactController#update_graph_metadata, which replaces ALL of a graph's
# metadata, so it first reads the current metadata with nebula's
# #get_graph_metadata and sends it back with only the GitHub issue changed. It
# runs against production GraphDB with the credential in nebula's encrypted
# Rails credentials. Run it with nebula's `rails runner`:
#
#   cd ~/repos/culturecreates/nebula
#   bin/rails runner <path>/link_source_log.rb [--dry-run] [--replace] <issue-url> <graph-uri> [<graph-uri> ...]
#
# --dry-run  show the current metadata and what would change; writes nothing.
# --replace  allow replacing a link to a different issue.
#
# If nebula renames or reshapes these methods, this script stops with an error
# instead of guessing: read app/controllers/artifact_controller.rb and update
# the calls below.

dry_run = !ARGV.delete("--dry-run").nil?
replace = !ARGV.delete("--replace").nil?
issue = ARGV.shift
graphs = ARGV
if issue.nil? || graphs.empty?
  abort "Usage: bin/rails runner link_source_log.rb [--dry-run] [--replace] <issue-url> <graph-uri> [<graph-uri> ...]"
end
abort "Not a GitHub issue URL: #{issue}" unless issue.match?(%r{\Ahttps://github\.com/[\w.\-]+/[\w.\-]+/issues/\d+\z})
graphs.each do |graph|
  abort "Not an Artsdata graph URI: #{graph}" unless graph.match?(%r{\Ahttp://kg\.artsdata\.ca/[\w.~\-/]+\z})
end

unless ArtifactController.method_defined?(:update_graph_metadata) && ArtifactController.method_defined?(:get_graph_metadata)
  abort "nebula's ArtifactController no longer has update_graph_metadata / get_graph_metadata. " \
        "Read app/controllers/artifact_controller.rb and update this script."
end

Rails.application.config.graph_api_endpoint = "https://db.artsdata.ca"
abort "No graph_db_basic_auth in nebula credentials" if Rails.application.credentials.graph_db_basic_auth.blank?

# The fields update_graph_metadata rewrites. If nebula adds one, sending only
# these would erase it, so stop.
FIELDS = %i[name maintainer github_issue rating_value rating_explanation].freeze

failed = false
graphs.each do |graph|
  controller = ArtifactController.new
  controller.request = ActionDispatch::TestRequest.create
  controller.response = ActionDispatch::TestResponse.new

  before = controller.get_graph_metadata(graph)
  unless before.keys.sort == FIELDS.sort
    abort "nebula's graph metadata fields changed (#{before.keys.join(', ')}). " \
          "Read app/controllers/artifact_controller.rb and update this script."
  end

  puts graph
  before.each { |field, value| puts "  #{field}: #{value.presence || '(none)'}" }

  if before[:github_issue] == issue
    puts "  already linked to #{issue}"
    next
  end
  if before[:github_issue].present? && !replace
    failed = true
    puts "  SKIPPED: already linked to a different issue; use --replace to change it"
    next
  end
  if dry_run
    puts "  would set github_issue: #{issue} (nothing written)"
    next
  end

  # Call the action directly (skipping the web login filter) with a stand-in request.
  controller.params = ActionController::Parameters.new(
    graph: graph,
    graph_name: before[:name],
    maintainer: before[:maintainer],
    github_issue: issue,
    rating_value: before[:rating_value],
    rating_explanation: before[:rating_explanation]
  )
  controller.update_graph_metadata

  if controller.flash.alert.present?
    failed = true
    puts "  FAILED: #{controller.flash.alert}"
    next
  end

  # Read back with nebula's own reader: only the issue may have changed.
  after = controller.get_graph_metadata(graph)
  if after == before.merge(github_issue: issue)
    puts "  linked to #{issue} (#{controller.flash.notice})"
  else
    failed = true
    puts "  FAILED: metadata is not as expected after the update: #{after.inspect}"
  end
end
exit(1) if failed
