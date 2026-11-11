# Reloads Databus artifacts into their Artsdata data feed graphs, without
# re-running the workflow that produced them.
#
# This script holds no API call of its own. It calls nebula's
# ArtifactController#push_version (the "Reload" button on the artifact page),
# so it always does whatever nebula currently does. Run it with nebula's
# `rails runner`:
#
#   cd ~/repos/culturecreates/nebula
#   bin/rails runner <path>/reload_graph.rb [--latest] [--dry-run] <graph-uri> [<graph-uri> ...]
#
# Default: reload the artifact version that is currently loaded in the graph.
# --latest: load the newest artifact version on the Databus instead (also the
#           way to load an artifact that has never been loaded).
# --dry-run: only print which artifact version would be loaded; change nothing.
#
# The Databus publisher is https://github.com/<handle>#this, as in nebula. The
# handle comes from GITHUB_HANDLE, or else from `gh api user`.
#
# If nebula renames or reshapes the methods used here, this script stops with
# an error instead of guessing: read app/controllers/artifact_controller.rb
# and update the calls below.

latest = !ARGV.delete("--latest").nil?
dry_run = !ARGV.delete("--dry-run").nil?
graphs = ARGV
abort "Usage: bin/rails runner reload_graph.rb [--latest] [--dry-run] <graph-uri> [<graph-uri> ...]" if graphs.empty?
graphs.each do |graph|
  unless graph.match?(%r{\Ahttp://kg\.artsdata\.ca/[\w.~\-]+/[\w.~\-]+/[\w.~\-]+\z}) && !graph.include?("/databus/")
    abort "Not a data feed graph URI (http://kg.artsdata.ca/<account>/<group>/<artifact>): #{graph}"
  end
end

needed = %i[push_version get_loaded_artifact_version get_artifact_versions user_uri]
missing = needed.reject { |m| ArtifactController.method_defined?(m) || ArtifactController.private_method_defined?(m) }
unless missing.empty?
  abort "nebula's ArtifactController no longer has #{missing.join(', ')}. " \
        "Read app/controllers/artifact_controller.rb and update this script."
end

require "action_controller/test_case"

handle = ENV["GITHUB_HANDLE"].to_s.strip
handle = `gh api user -q .login 2>/dev/null`.strip if handle.empty?
abort "No GitHub handle: set GITHUB_HANDLE or sign in with gh." if handle.empty?

# Production endpoints, as in nebula's config/environments/production.rb.
Rails.application.config.graph_api_endpoint = "https://db.artsdata.ca"
Rails.application.config.artsdata_databus_endpoint = "https://api.artsdata.ca/databus"

failed = false
graphs.each do |graph|
  artifact_uri = graph.sub("http://kg.artsdata.ca/", "http://kg.artsdata.ca/databus/")

  # Call the action directly (skipping the web login filter) with a stand-in request.
  controller = ArtifactController.new
  controller.request = ActionDispatch::TestRequest.create
  controller.response = ActionDispatch::TestResponse.new
  controller.request.session = ActionController::TestSession.new(handle: handle) # nebula builds the publisher URI from this

  version =
    if latest
      controller.send(:get_artifact_versions, artifact_uri).first
    else
      controller.send(:get_loaded_artifact_version, graph)
    end
  if version.nil?
    failed = true
    puts latest ? "FAILED #{graph}: no artifact versions found for #{artifact_uri}" :
                  "FAILED #{graph}: nothing is loaded in this graph (use --latest to load the newest version)"
    next
  end

  if dry_run
    puts "would reload #{graph} with #{version.dataset_uri} as #{controller.send(:user_uri)}"
    next
  end

  controller.params = ActionController::Parameters.new(artifactUri: artifact_uri, artifactVersionUri: version.dataset_uri.to_s)
  controller.push_version

  if controller.flash.alert.present?
    failed = true
    puts "FAILED #{graph}: #{controller.flash.alert}"
  else
    puts "reloaded #{graph}: #{controller.flash.notice}"
  end
end
exit(1) if failed
