print("Sports Prop Projections  Phase 1 setup complete")
from projections import points_prediction

avg=float(input("Enter player average: "))
line=float(input("Enter Vegas line: "))

decision,confidence=points_prediction(avg, line)

print(f'The prediction is to take the {decision}')
print(f'confidence level: {confidence}%')



