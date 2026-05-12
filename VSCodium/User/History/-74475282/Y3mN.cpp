#include <clocale>                              //Библиотеки
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
    

        if (file) {                             //когда пароль нашло 
            std::string line;
            while (getline(file, line))
            if (line == SearchedPassword) {
                std::cout << "Пароль найден: [" << line << "]" << std::endl;
                found = true;
                break;
            }
        
             if (!found) {                       //когда не нашло
                 std::cout << "Ошибка, пароль не найден!" << std::endl;
            }
            file.close();

        } else {                                 //когда фаила с паролями нет 
                std::cout << "Ошибка, фаил не открывается!" << std::endl;
        
    return 0;
    }

} 