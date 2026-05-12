#include <iostream>

int main() {
   setlocale(LC_ALL, "RU");

   //new_shit

    short a1 = 14; //-32k till 32k / 2 bytes
    int a2 = 13;   //-2B till 2B / 4 bytes
    long a3 = 12;  // ДОХУЯ / 8 bytes

    unsigned short b1 = 14; //0 till 64k / 2 bytes
    unsigned int b2 = 13;   //0 till 4B / 4 bytes
    unsigned long b3 = 12;  // ДОХУЯ / 8 bytes
    
    return 0;
}