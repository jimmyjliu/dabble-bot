import re
from PIL import Image
import pytesseract

def parse_number(value):
    """
    Convert a string to an int if possible, otherwise to a float.
    :param value: The string value to parse
    :return: int or float
    """
    try:
        return int(value)  # Try to convert to integer
    except ValueError:
        return float(value)  # Fallback to float
    
def clean_player_name(raw_name):
    """
    Cleans the player name by removing unwanted substrings like 'Headshot'.
    :param raw_name: The raw player name string
    :return: Cleaned player name
    """
    return raw_name.replace("Headshot", "").strip()

def clean_team_name(raw_team):
    """
    Cleans the team name by removing concatenated strings like 'LionsLionsRB'.
    :param raw_team: The raw team/position string
    :return: Cleaned team name
    """
    # Assume the last two characters represent the position (e.g., 'RB', 'WR', 'TE')
    if len(raw_team) > 2:
        team_name = raw_team[:-2].strip()  # Everything except the last 2 chars
    else:
        team_name = raw_team.strip()
    return team_name

def parse_projections_by_position(lines, i, position):
    """
    Parse projection fields based on the player's position.
    :param lines: The list of all lines in the file
    :param i: The current line index
    :param position: The player's position (RB, WR, TE, etc.)
    :return: A dictionary of projections and the updated line index
    """
    projections = {}

    try:
        if position == "RB":
            projections["carries"] = parse_number(lines[i].strip())
            i += 1
            projections["yards"] = parse_number(lines[i].strip())
            i += 1
            projections["average"] = parse_number(lines[i].strip())
            i += 1
            projections["td"] = parse_number(lines[i].strip())
            i += 1
            projections["receptions"] = parse_number(lines[i].strip())
            i += 1
            projections["receiving_yards"] = parse_number(lines[i].strip())
            i += 1
            projections["receiving_td"] = parse_number(lines[i].strip())
            i += 1
            projections["fantasy_points"] = parse_number(lines[i].strip())
            i += 1

        elif position in {"WR", "TE"}:
            projections["targets"] = parse_number(lines[i].strip())
            i += 1
            projections["receptions"] = parse_number(lines[i].strip())
            i += 1
            projections["receiving_yards"] = parse_number(lines[i].strip())  # Fix here
            i += 1
            projections["average"] = parse_number(lines[i].strip())
            i += 1
            projections["td"] = parse_number(lines[i].strip())
            i += 1
            projections["carries"] = parse_number(lines[i].strip())
            i += 1
            projections["rush_yards"] = parse_number(lines[i].strip())
            i += 1
            projections["rush_td"] = parse_number(lines[i].strip())
            i += 1
            projections["fantasy_points"] = parse_number(lines[i].strip())
            i += 1

    except IndexError:
        print(f"Error parsing projections for position: {position} at line {i}")

    return projections, i

def parse_projections_from_files(file_path_team1, file_path_team2):
    """
    Parse player names and weekly projections from two text files (one for each team).
    :param file_path_team1: Path to the text file containing player data for team 1
    :param file_path_team2: Path to the text file containing player data for team 2
    :return: A dictionary with parsed players grouped by team
    """
    def clean_player_name(raw_name):
        """
        Cleans the player name by removing unwanted substrings like 'Headshot'.
        """
        return raw_name.replace("Headshot", "").strip()

    def clean_team_name(raw_team):
        """
        Cleans the team name by removing concatenated strings like 'LionsLionsRB'.
        """
        if len(raw_team) > 2:
            team_name = raw_team[:-2].strip()
        else:
            team_name = raw_team.strip()
        return team_name

    def parse_team(file_path):
        """
        Parse players for a single team.
        """
        with open(file_path, "r") as file:
            lines = file.readlines()

        players = []
        i = 0  # Line index

        while i < len(lines):
            line = lines[i].strip()

            # Check for player rank line
            if line.isdigit():
                player = {}
                i += 1  # Move to the player's name
                
                # Parse player name and clean it
                raw_player_name = lines[i].strip()
                player["name"] = clean_player_name(raw_player_name)
                
                i += 2  # Skip to team and position
                
                # Parse team and position, clean team name
                raw_team_position = lines[i].strip()
                player["team"] = clean_team_name(raw_team_position)
                player["position"] = raw_team_position[-2:].strip()  # Last 2 chars for position
                
                # Advance to WEEK 13 PROJECTIONS
                while i < len(lines) and "WEEK 13 PROJECTIONS" not in lines[i]:
                    i += 1
                
                if i < len(lines) and "WEEK 13 PROJECTIONS" in lines[i]:
                    i += 1  # Move to projections
                    
                    # Parse projections based on position
                    player["projections"], i = parse_projections_by_position(lines, i, player["position"])

                # Append the parsed player to the list
                players.append(player)

            i += 1  # Move to the next line

        return players

    # Parse both teams
    team1_players = parse_team(file_path_team1)
    team2_players = parse_team(file_path_team2)

    return {"team1": team1_players, "team2": team2_players}

def extract_text_from_image(image_path):
    """
    Perform OCR on an image to extract text.
    :param image_path: Path to the image file
    :return: Extracted text as a string
    """
    # Open the image
    image = Image.open(image_path)

    # Perform OCR
    text = pytesseract.image_to_string(image)

    return text

def parse_line_data(extracted_text):
    """
    Parse player line data from OCR-extracted text.
    :param extracted_text: Raw text extracted via OCR
    :return: A dictionary of players and their lines
    """
    lines = extracted_text.splitlines()
    combined_lines = []
    current_player = ""

    # Combine related lines
    for line in lines:
        line = line.strip()
        if not line:
            continue  # Skip empty lines
        if "(" in line and ")" in line:  # Likely a player line
            current_player = line
        elif "Receiving Yards" in line:  # Line data
            combined_lines.append(f"{current_player} {line}")
            current_player = ""  # Reset after combining

    # Parse combined lines
    player_lines = {}
    for line in combined_lines:
        # Match lines like "Amon-Ra St. Brown (WR) 70.5 Receiving Yards"
        match = re.match(r"(.+?)\s\((.+?)\)\s([\d.]+)\sReceiving Yards", line)
        if match:
            player_name = match.group(1).strip()
            position = match.group(2).strip()
            line_value = float(match.group(3).strip())
            player_lines[player_name] = {"position": position, "line": line_value}

    return player_lines

def compare_projections_with_lines(projections, player_lines):
    """
    Compare projections with line data to calculate deltas and suggest bets.
    :param projections: List of player projections
    :param player_lines: Dictionary of player line data
    :return: List of comparison results
    """
    results = []

    for player in projections:
        name = player["name"]
        projected_yards = player["projections"].get("receiving_yards")  # None if missing

        if name in player_lines:
            line_value = player_lines[name]["line"]

            if projected_yards is None:
                # Handle missing projection
                delta = None
                suggestion = "N/A (Missing Projections)"
            else:
                # Calculate delta and suggestion
                delta = projected_yards - line_value
                suggestion = "Over" if delta > 0 else "Under"

            results.append({
                "name": name,
                "position": player["position"],
                "projected_yards": projected_yards if projected_yards is not None else "N/A",
                "line": line_value,
                "delta": delta if delta is not None else "N/A",
                "suggestion": suggestion
            })

    return results


def main():
    """
    Main function to integrate line data with player projections and calculate deltas.
    """
    # Example file paths
    file_path_team1 = "projections/team1.txt"  # Replace with actual file path for team 1
    file_path_team2 = "projections/team2.txt"  # Replace with actual file path for team 2
    image_path = "images/lines1.jpg"  # Replace with the actual image file path

    # Parse projections from text files
    game_data = parse_projections_from_files(file_path_team1, file_path_team2)
    projections = game_data["team1"] + game_data["team2"]

    # Perform OCR and parse line data
    extracted_text = extract_text_from_image(image_path)
    player_lines = parse_line_data(extracted_text)

    # Compare projections with line data
    comparison_results = compare_projections_with_lines(projections, player_lines)

    # Sort the results by absolute delta values in descending order
    sorted_results = sorted(
        comparison_results,
        key=lambda x: abs(x['delta']) if isinstance(x['delta'], (int, float)) else -float('inf'),
        reverse=True
    )

    # Display the sorted results
    print("Comparison Results (Sorted by Delta):")
    for result in sorted_results:
        print(f"Player: {result['name']}")
        print(f"  Position: {result['position']}")
        print(f"  Projected Yards: {result['projected_yards']}")
        print(f"  Line: {result['line']}")
        if isinstance(result['delta'], (int, float)):
            print(f"  Delta: {result['delta']:.2f}")
        else:
            print(f"  Delta: {result['delta']}")
        print(f"  Suggestion: {result['suggestion']}")
        print("-" * 30)

if __name__ == "__main__":
    main()