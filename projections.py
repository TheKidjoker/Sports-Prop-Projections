## this function should take in two parameters: The players avearage points per games the vegas line for said player
def points_prediction(player_pointsavg, vegas_line):

    difference = player_pointsavg - vegas_line
    probability = 0.5 + (difference / vegas_line)
    probability= max(0, min(probability, 1))

    if probability >= 0.55:
        return "Over", round(probability* 100,1) 
    
    if probability <= 0.45:
        return "Under", round((1 - probability) * 100,1)
    
    else: return 'PASS ON THIS BET'


    if player_pointsavg > vegas_pointsavg:
        return "Over"
    if player_pointsavg < vegas_pointsavg:
        return "Under"
    else:
        return "PASS", round(probability * 100, 1)
    

def get_player_data():
    avg=float(input("Enter player average: "))
    line=float(input("Enter Vegas line: ")) 
    return avg, line


def cover_rate(game_points, vegas_line):
    over_hits=0
    under_hits=0
    push=0

    for points in game_points:
        if points > vegas_line:
            over_hits += 1
        elif points < vegas_line:
            under_hits += 1
        elif points == vegas_line:
            push += 1

    total_games= len(game_points)
    over_rate = round((over_hits / total_games) * 100, 1)
    under_rate = round((under_hits / total_games) * 100, 1)
    push_rate = round((push / total_games) * 100, 1)

    return over_rate, under_rate, push_rate