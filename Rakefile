# Rakefile

require 'rake/testtask'

# Define a task to run a specific test file
# rake test_single TEST_FILE=path/to/file.rb
task :test_single do
  test_file = ENV['TEST_FILE']

  if test_file.nil? || test_file.empty?
    puts "Please provide a test file to run using TEST_FILE=path/to/test_file.rb"
  else
    Rake::TestTask.new do |t|
      t.libs << 'test'
      t.pattern = test_file
      t.warning = false
    end
    Rake::Task['test'].execute
  end
end

# Define a task to run all test files
# rake test_all
task :test_all do
  Rake::TestTask.new do |t|
    t.libs << 'test'
    t.pattern = 'tests/*_test.rb'
    t.warning = false
  end
  begin
    Rake::Task['test'].execute
  rescue => e
    puts "Some tests did not pass. #{e}"
  end
end

task default: :test_all
