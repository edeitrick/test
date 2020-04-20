#include <stdio.h> 
int main (void) 
{ 
  int k; 
  double x, y, z;

  printf( "Enter an integer: "); 
  scanf( "%i" k ); 
  printf( "Enter a double: "); 
  scanf( "%d", &x ); 
  printf( "Enter two doubles:" ); 
  scanf( "%lg%lg", &y, &z ); 
  printf( "k= %i X= %g \n", k, x ); 
  printf( "y= %g z= %g \n", &y, &z );
}