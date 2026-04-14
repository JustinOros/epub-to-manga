def group_into_pages(scenes, mode="normal"):
    if mode == "tiny":
        return [[s] for s in scenes]
    pages = []
    temp = []
    for s in scenes:
        temp.append(s)
        if len(temp) == 3:
            pages.append(temp)
            temp = []
    if temp:
        pages.append(temp)
    return pages
