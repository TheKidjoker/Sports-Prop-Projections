print("Sports Prop Projections  Phase 1 setup complete")
from projections import cover_rate, points_prediction
recent_games = [22, 18, 25, 30, 27, 20, 28, 24, 19, 21]
avg=float(input("Enter player average: "))
line=float(input("Enter Vegas line: "))

decision,confidence=points_prediction(avg, line)

print(f'The prediction is to take the {decision}')
print(f'confidence level: {confidence}%')

over_rate, under_rate, push = cover_rate(recent_games, line)

print(f'Over rate is: {over_rate}%')
print(f'Under rate is: {under_rate}%')
print(f'Push rate is: {push}%')