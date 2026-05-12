
int main() {
   

   //циферки
    short a1 = 14; //-32k till 32k / 2 bytes
    int a2 = 13;   //-2B till 2B / 4 bytes
    long a3 = 12;  // ДОХУЯ / 8 bytes

    unsigned short b1 = 14; //0 till 64k / 2 bytes
    unsigned int b2 = 13;   //0 till 4B / 4 bytes
    unsigned long b3 = 12;  // ДОХУЯ / 8 bytes

    //циферки говна
    float c1 = 14.1488f; //типо инт но с точкой
    double c2 = 13.1488f; //типо лонг но с точкой

    //сивол
    char d1 = '&'; //символ (свастон нельзя)

    //логика
    bool stoit = true; //тру фолс

    return 0;
}