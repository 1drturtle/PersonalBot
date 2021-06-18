FROM python:3.9-buster

RUN apt update
RUN apt install procinfo

WORKDIR /pbot

ADD ./requirements.txt /pbot/requirements.txt
RUN pip install -r requirements.txt

ADD /bot /pbot

ENTRYPOINT ["python", "bot.py"]