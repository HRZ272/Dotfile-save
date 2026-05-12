with open('DEMO_17.txt') as f:
    nums = [int(x.strip()) for x in f if x.strip()]

two_digit = [x for x in nums if 10 <= x <= 99]
print(min(two_digit))