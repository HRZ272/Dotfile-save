#include <clocale>    //Библиотеки
#include <iostream>
#include <fstream>
#include <string>

int main () {
    setlocale(LC_ALL, "RU");
    
    std::string SearchedPassword;               //все переменные
    std::cout << "Введите пароль для поиска: ";
    std::cin >> SearchedPassword;
    std::ifstream file("passwords.txt");
    bool found = false;
    int found2 = 0;
    int notfound2 = 0;

        if (file) {                             //когда пароль нашло 
            std::string line;
            while (getline(file, line))
            if (line == SearchedPassword) {
                std::cout << "Пароль найден: [" << line << "]" << std::endl;
                found = true;
                found2 = 1;
                break;
            }
        
             if (!found) {                       // когда не нашло
                 std::cout << "Ошибка, пароль не найден!" << std::endl;
                 notfound2 = 1;
            }

            if (found == 0 && notfound2 == 0) {  //мой шедевро код когда фаила с паролями нет
                std::cout << "Ошибка, фаил не открывается!";
        }
    return 0;
    }

} 