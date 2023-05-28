import json

# Open the input file for reading
with open('conductor-tuning.jsonl', 'r') as file:
    # Open the output file for writing
    with open('clean.json', 'w') as output_file:
        # Create a list to store the output entries
        output_entries = []
        
        # Loop through each line in the file
        for line in file:
            # Check if the line contains JSON data
            if 'prompt' in line and 'completion' in line:
                # Extract the JSON data from the line
                start_index = line.index('{')
                end_index = line.rindex('}') + 1
                json_data = line[start_index:end_index]
                
                # Parse the JSON data
                data = json.loads(json_data)
                
                # Create the desired output
                output = {
                    "instruction": data["prompt"],
                    "input": "",
                    "output": data["completion"]
                }
                
                # Append the output entry to the list
                output_entries.append(output)
        
        # Write the output entries to the file
        output_json = json.dumps(output_entries, indent=4)
        output_file.write(output_json)

print("Output has been written to clean.json")
