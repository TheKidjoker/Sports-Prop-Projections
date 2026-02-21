from projections import points_prediction, cover_rate
from api_client import get_player_recent_points, find_game_by_team, get_game_spread
from time_slots import classify_slot, get_slot_label
from line_movement import detect_movement, confirms_slot


def parse_time(time_str):
    """
    Parses a time string like '7:00 PM' into (hour, minute) in 24hr format.
    """
    time_str = time_str.strip().upper()
    is_pm = "PM" in time_str
    is_am = "AM" in time_str
    time_str = time_str.replace("PM", "").replace("AM", "").strip()

    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0

    if is_pm and hour != 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0

    return hour, minute


def main():
    print("Sports Prop Projections – Phase 1 setup complete\n")

    # --- User Inputs ---
    player_name = input("Enter player name (e.g., LeBron James): ")

    day_of_week = input("Enter day of the week (e.g., Monday): ")
    game_time = input("Enter game start time in PST (e.g., 7:00 PM): ")

    try:
        vegas_line = float(input("Enter Vegas line: "))
        games = int(input("How many recent games should be used? (e.g., 5): "))
    except ValueError:
        print("Invalid input. Please enter numeric values for line and games.")
        return

    # Parse game time to 24hr format
    hour, minute = parse_time(game_time)
    slot_type = classify_slot(day_of_week, hour, minute)
    slot_label = get_slot_label(slot_type)

    # --- Line Movement Check ---
    line_confirmed = False
    team_name = input("Enter one team playing in the game (e.g., Lakers): ")

    if team_name.strip():
        event_id = find_game_by_team(team_name)

        if event_id:
            opening, current = get_game_spread(event_id)

            if opening is not None and current is not None:
                movement, magnitude = detect_movement(opening, current)
                confirmed = confirms_slot(movement, slot_type)
                line_confirmed = confirmed

                print(f"\nLine Movement:")
                print(f"  Opening spread: {opening:+.1f}")
                print(f"  Current spread: {current:+.1f}")
                print(f"  Movement: {movement} ({magnitude:.1f} pts)")
                print(f"  Confirms slot: {'YES' if confirmed else 'NO'}")
                if confirmed:
                    print("  +5 confidence boost applied")
            else:
                print("\nLine Movement: Spread data not available for this game.")
        else:
            print(f"\nLine Movement: No game found today for '{team_name}'.")
    else:
        print("\nLine Movement: Skipped (no team entered).")

    # --- Fetch real NBA data ---
    recent_games = get_player_recent_points(player_name, games)

    if not recent_games or len(recent_games) == 0:
        print("No recent game data available for this player.")
        return

    print(f"\nRecent game points for {player_name}: {recent_games}")

    # --- Model Prediction ---
    player_avg = sum(recent_games) / len(recent_games)
    decision, confidence = points_prediction(player_avg, vegas_line, slot_type, line_confirmed)

    print(f"\nTime Slot: {slot_label}")
    print("\nModel prediction:")
    print(f"Decision: {decision}")
    print(f"Confidence: {confidence}%")

    # --- Historical Cover Rates ---
    over_rate, under_rate, push_rate = cover_rate(recent_games, vegas_line)

    print("\nHistorical performance:")
    print(f"OVER rate:  {over_rate}%")
    print(f"UNDER rate: {under_rate}%")
    print(f"PUSH rate:  {push_rate}%")


if __name__ == "__main__":
    main()
