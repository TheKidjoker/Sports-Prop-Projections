## this function should take in two parameters: The players avearage points per games the vegas line for said player
def points_prediction(player_pointsavg, vegas_pointsavg):

    difference = player_pointsavg - vegas_pointsavg
    probability = 0.5 + (difference / vegas_pointsavg)
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
    

