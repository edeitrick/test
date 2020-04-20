{Check It!|assessment}(code-output-compare-3758561617)
# Programming Question

 Write a program to decide the outcome of the simplified version of the blackjack game.
 Your program repeatedly gets a card number (1-13) from input. 
 The program ends if the total values of cards so far is greater than or equal to 21. 
 If the value is greater than 21 it prints "You lost!" otherwise (equals to 21) it prints "You won!".
 If the player enters a card number that is not between 1 and 13, the program simply ignore that number.
 
 
 Sample output:
 Enter a number between 1 and 13: 23
 Enter a number between 1 and 13: 2
 Enter a number between 1 and 13: 3
 Enter a number between 1 and 13: 10
 Enter a number between 1 and 13: 6
 You won!
 



{Compile}(gcc quiz1.c -o quiz1)

{Test your code | terminal}(./quiz1)