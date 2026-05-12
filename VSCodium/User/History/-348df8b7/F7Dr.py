with open('DEMO_17.txt') as f:
    n = [int(x.strip()) for x in f if x.strip()]

two_digit = [x for x in n if 10 <= x <= 99]
print(min(two_digit))