with open('DEMO_17.txt') as f:
    nums = [int(x.strip()) for x in f if x.strip()]

c = len(nums)

# минимальный двузначный
min_two = 100
for i in range(c):
    if 10 <= nums[i] <= 99:
        if nums[i] < min_two:
            min_two = nums[i]

count = 0
max_sum = 0

for i in range(c - 1):
    if (10 <= nums[i] <= 99 and (nums[i+1] < 10 or nums[i+1] > 99)) or \
       (10 <= nums[i+1] <= 99 and (nums[i] < 10 or nums[i] > 99)):
        s = nums[i] + nums[i+1]
        if s % min_two == 0:
            count += 1
            if s > max_sum:
                max_sum = s

print(count)
print(max_sum)