# AI Fix #546
Fix ISO control numbers interpretation
```diff
--- a/iso_parser.py
+++ b/iso_parser.py
@@ -10,7 +10,7 @@
 # Parse ISO control numbers
 def parse_iso_control_numbers(numbers):
-    return [float(num) for num in numbers]
+    return [str(num) for num in numbers]

 # Example usage:
@@ -20,5 +20,5 @@
 def main():
     numbers = ["7.1", "7.10", "8.1", "8.10"]
-    parsed_numbers = [float(num) for num in numbers]
+    parsed_numbers = parse_iso_control_numbers(numbers)
     print(parsed_numbers)

-if __name__ == "__main__":
-    main()
\ No newline at end of file
+if __name__ == "__main__":
+    main()
```