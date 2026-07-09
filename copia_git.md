# Antes de empezar en casa
dd /Volumes/Disco/proyectos/research_agent
git pull

# Antes de empezar en trabajo
git pull

# En casa
cd /Volumes/Disco/proyectos/research_agent
git add ESTADO.md NOTAS_PENDIENTES.md
git commit -m "texto de lo que se ha realizado"
git push

o mejor aún:
git push origin main


# En pciq22
cd ~/proyectos/research_agent
git pull

# Cuando git pull no funcione hacer:
git fetch origin
git pull origin main