with open('DEMO_17.txt') as f:
    nums = [int(x.strip()) for x in f if x.strip()]

two_digit = [x for x in nums if 10 <= x <= 99]
min_two = min(two_digit)

count = 0
max_sum = 0

for i in range(len(nums) - 1):
    a, b = nums[i], nums[i+1]
    a_two = 10 <= a <= 99
    b_two = 10 <= b <= 99
    if a_two ^ b_two:  # ровно один двузначный
        s = a + b
        if s % min_two == 0:
            count += 1
            if s > max_sum:
                max_sum = s

print(f"Минимальный двузначный: {min_two}")
print(f"Количество пар: {count}")
print(f"Максимальная сумма: {max_sum}")